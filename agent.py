#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM with tools to answer questions using wiki, source code, and live API.

Usage:
    uv run agent.py "Your question here"

Output:
    {"answer": "...", "source": "...", "tool_calls": [...]}
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

# === Configuration ===


class AgentSettings(BaseModel):
    """Configuration loaded from .env.agent.secret and .env.docker.secret."""

    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"
    lms_api_key: str = ""  # Loaded from .env.docker.secret
    agent_api_base_url: str = "http://localhost:42002"  # Backend API URL


def load_settings() -> AgentSettings:
    """Load and validate agent configuration from multiple env files."""
    # Load LLM config from .env.agent.secret
    agent_env_file = Path(__file__).parent / ".env.agent.secret"
    if agent_env_file.exists():
        load_dotenv(agent_env_file)

    # Load LMS API key from .env.docker.secret
    docker_env_file = Path(__file__).parent / ".env.docker.secret"
    if docker_env_file.exists():
        load_dotenv(docker_env_file, override=False)

    try:
        return AgentSettings(
            llm_api_key=os.environ["LLM_API_KEY"],
            llm_api_base=os.environ["LLM_API_BASE"],
            llm_model=os.environ.get("LLM_MODEL", "qwen3-coder-plus"),
            lms_api_key=os.environ.get("LMS_API_KEY", ""),
            agent_api_base_url=os.environ.get(
                "AGENT_API_BASE_URL", "http://localhost:42002"
            ),
        )
    except KeyError as e:
        print(f"Error: Missing environment variable {e}", file=sys.stderr)
        sys.exit(1)


# === Tool Definitions ===

PROJECT_ROOT = Path(__file__).parent


def validate_path(path: str) -> Path:
    """Validate and resolve a path safely (no directory traversal)."""
    # Check for directory traversal attempts
    if ".." in path:
        raise ValueError(f"Invalid path: directory traversal not allowed")

    # Resolve the path relative to project root
    full_path = (PROJECT_ROOT / path).resolve()

    # Ensure the path is within project root
    try:
        full_path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Invalid path: must be within project directory")

    return full_path


def tool_read_file(path: str) -> str:
    """Read a file from the project repository."""
    try:
        safe_path = validate_path(path)
        if not safe_path.exists():
            return f"Error: File not found: {path}"
        if not safe_path.is_file():
            return f"Error: Not a file: {path}"
        return safe_path.read_text()
    except ValueError as e:
        return f"Error: {e}"


def tool_list_files(path: str) -> str:
    """List files and directories at a given path."""
    try:
        safe_path = validate_path(path)
        if not safe_path.exists():
            return f"Error: Directory not found: {path}"
        if not safe_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = sorted(safe_path.iterdir())
        lines = [entry.name for entry in entries]
        return "\n".join(lines)
    except ValueError as e:
        return f"Error: {e}"


def tool_query_api(
    method: str,
    path: str,
    body: str | None = None,
    settings: AgentSettings | None = None,
) -> str:
    """Call the backend API with LMS_API_KEY authentication."""
    if settings is None:
        settings = load_settings()

    if not settings.lms_api_key:
        return "Error: LMS_API_KEY not configured. Set it in .env.docker.secret."

    base_url = settings.agent_api_base_url
    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {settings.lms_api_key}",
        "Content-Type": "application/json",
    }

    print(f"Calling API: {method} {url}", file=sys.stderr)

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                data = json.loads(body) if body else {}
                response = client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            elif method.upper() == "PATCH":
                data = json.loads(body) if body else {}
                response = client.patch(url, headers=headers, json=data)
            else:
                return f"Error: Unsupported method: {method}"

            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result)

    except httpx.TimeoutException:
        return f"Error: API request timed out after 30 seconds"
    except httpx.ConnectError as e:
        return f"Error: Cannot connect to API at {url}: {e}"
    except Exception as e:
        return f"Error: {e}"


# Tool registry
TOOLS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "query_api": tool_query_api,
}


# === Tool Schemas for LLM ===


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return OpenAI-compatible tool schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file from the project",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories in a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Call the backend API and return the response. Use this for live data (item counts, scores), API behavior (status codes), testing endpoints, or checking analytics.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, PUT, DELETE, PATCH)",
                            "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                        },
                        "path": {
                            "type": "string",
                            "description": "API path (e.g., '/items/', '/analytics/completion-rate')",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body (for POST/PUT/PATCH)",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


# === System Prompt ===

SYSTEM_PROMPT = """You are a documentation and system agent that answers questions using:
1. Project wiki (via list_files and read_file)
2. Source code (via read_file)
3. Live backend API (via query_api)

Tools available:
- list_files(path): List files and directories in a directory
- read_file(path): Read the contents of a file from the project
- query_api(method, path, body): Call the backend API and return the response. The API key is automatically included.

Tool selection guide:
- Use list_files/read_file for: wiki documentation, source code, configuration files (docker-compose.yml, Dockerfile, etc.)
- Use query_api for: live data (item counts, scores), API behavior (status codes, error messages), testing endpoints, checking analytics

Process:
1. For wiki questions → use list_files to discover wiki files, then read_file to find the answer
2. For source code questions → use read_file on backend/ files or configuration files
3. For live data questions → use query_api to query the running API
4. For API behavior questions → use query_api to test endpoints (e.g., check status codes)
5. For bug diagnosis → use query_api to see the error, then read_file to examine the source code
6. For comparison questions → read both codebases and compare their approaches

API Authentication Knowledge:
- The backend API requires authentication via Bearer token (LMS_API_KEY)
- Requests without authentication typically return HTTP 401 (Unauthorized) or 403 (Forbidden)
- When asked about unauthenticated requests, you can infer that 401/403 would be returned

Data Counting:
- When querying list endpoints (e.g., /items/, /learners/), COUNT the results
- Report the exact number of items/learners/entries returned
- Example: "There are 44 items in the database" (count the array length)

Bug Detection in Analytics Code:
- When asked about bugs or risky operations in analytics code, look for:
  - Division operations (risk: ZeroDivisionError) - check for division by zero guards
  - Sorting with None values (risk: TypeError) - check for None handling before sorted()
  - Aggregation on empty lists (risk: errors or wrong results)
  - Missing error handling for edge cases
- Always read the full file to find ALL potential issues

Error Handling Analysis:
- When comparing error handling, look for:
  - Try/except blocks and what exceptions they catch
  - Return values on error (None, error dict, raised exceptions)
  - Logging of errors
  - Whether errors are silenced or propagated
  - Idempotency checks (e.g., checking if data exists before inserting)

Guidelines:
- Only make necessary tool calls - don't over-use tools
- Always provide a source reference when using read_file (format: path/to/file.md#section-anchor)
- For query_api results, mention the endpoint queried
- The source field should reference the file path when using read_file (e.g., wiki/git-workflow.md)
- For query_api answers, source can be empty or mention the endpoint
- IMPORTANT: Always give complete, final answers - never say "let me check" or "I need to" without actually completing the thought
- When you've gathered enough information, provide a comprehensive final answer
- Don't leave answers hanging - finish your explanation
- For counting questions, provide the exact number
- For bug questions, identify the specific line or operation causing the issue
- For comparison questions, clearly state the differences

When providing a source reference:
- Use the file path (e.g., wiki/git-workflow.md, backend/app/routers/items.py)
- Add a section anchor if applicable (e.g., #resolving-merge-conflicts)
- Format: path/to/file.md#section-name
"""


# === Agentic Loop ===

MAX_TOOL_CALLS = 15


def execute_tool(
    tool_name: str, args: dict[str, Any], settings: AgentSettings | None = None
) -> str:
    """Execute a tool and return the result."""
    if tool_name not in TOOLS:
        return f"Error: Unknown tool: {tool_name}"

    try:
        func = TOOLS[tool_name]
        # Pass settings to query_api
        if tool_name == "query_api":
            return func(**args, settings=settings)
        return func(**args)
    except Exception as e:
        return f"Error executing {tool_name}: {e}"


def call_llm(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    settings: AgentSettings,
) -> dict[str, Any]:
    """Send messages to LLM and return the response."""
    url = f"{settings.llm_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "tools": tool_schemas,
        "tool_choice": "auto",
    }

    print(f"Calling LLM at {url}", file=sys.stderr)

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        print("Error: Request timed out after 60 seconds", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: HTTP {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error calling LLM: {e}", file=sys.stderr)
        sys.exit(1)


def run_agentic_loop(
    question: str, settings: AgentSettings
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Run the agentic loop.

    Returns:
        (answer, source, tool_calls)
    """
    # Initialize message history
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_schemas = get_tool_schemas()
    all_tool_calls: list[dict[str, Any]] = []
    tool_call_count = 0
    last_source = ""

    print(f"Question: {question}", file=sys.stderr)

    while tool_call_count < MAX_TOOL_CALLS:
        # Call LLM
        response_data = call_llm(messages, tool_schemas, settings)

        # Get the assistant message
        choice = response_data["choices"][0]
        message = choice["message"]

        # Check for tool calls
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            # No tool calls - this is the final answer
            # Use 'or ""' because content can be null (not just missing)
            answer = message.get("content") or ""
            print(f"Answer: {answer}", file=sys.stderr)

            # Try to extract source from answer if not already set
            if not last_source and answer:
                # Look for wiki/... patterns in the answer
                import re

                match = re.search(r"(wiki/[\w\-/.]+\.md(?:#[\w\-]+)?)", answer)
                if match:
                    last_source = match.group(1)

            return answer, last_source, all_tool_calls

        # Add assistant message with tool calls to history
        messages.append(message)

        # Execute each tool call
        for tool_call in tool_calls:
            tool_call_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])

            print(f"Executing tool: {tool_name}({tool_args})", file=sys.stderr)

            # Execute the tool
            result = execute_tool(tool_name, tool_args, settings)

            # Record the tool call
            tool_call_record = {
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            }
            all_tool_calls.append(tool_call_record)

            # Track source from read_file calls
            if tool_name == "read_file" and "Error" not in result:
                path_arg = tool_args.get("path", "")
                # Track any file reference, not just wiki/
                if path_arg.endswith((".md", ".py", ".yml", ".yaml", ".json", ".txt")):
                    last_source = path_arg

            # Add tool result to message history
            messages.append(
                {
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call_id,
                }
            )

            tool_call_count += 1

            if tool_call_count >= MAX_TOOL_CALLS:
                print(
                    f"Warning: Reached maximum tool calls ({MAX_TOOL_CALLS})",
                    file=sys.stderr,
                )
                break

    # Max iterations reached - get final answer
    if all_tool_calls:
        # Use the last file read as source
        answer = message.get("content", "I reached the maximum number of tool calls.")
        print(f"Answer (max calls reached): {answer}", file=sys.stderr)
        return answer, last_source, all_tool_calls

    # Fallback
    return "Unable to answer.", "", all_tool_calls


# === Main Entry Point ===


def main() -> None:
    """Main entry point."""
    # Parse command-line argument
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    settings = load_settings()

    # Run agentic loop
    answer, source, tool_calls = run_agentic_loop(question, settings)

    # Build output
    output = {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }

    # Output JSON to stdout
    print(json.dumps(output))


if __name__ == "__main__":
    main()
