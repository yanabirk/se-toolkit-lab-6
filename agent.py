#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM with tools to answer questions using the project wiki.

Usage:
    uv run agent.py "Your question here"

Output:
    {"answer": "...", "source": "...", "tool_calls": [...]}
"""

import json
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

# === Configuration ===


class AgentSettings(BaseModel):
    """Configuration loaded from .env.agent.secret."""

    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"


def load_settings() -> AgentSettings:
    """Load and validate agent configuration."""
    env_file = Path(__file__).parent / ".env.agent.secret"
    if not env_file.exists():
        print(f"Error: {env_file} not found", file=sys.stderr)
        print("Run: cp .env.agent.example .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_file)

    import os

    try:
        return AgentSettings(
            llm_api_key=os.environ["LLM_API_KEY"],
            llm_api_base=os.environ["LLM_API_BASE"],
            llm_model=os.environ.get("LLM_MODEL", "qwen3-coder-plus"),
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


# Tool registry
TOOLS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
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
    ]


# === System Prompt ===

SYSTEM_PROMPT = """You are a documentation agent that answers questions using the project wiki.

Tools available:
- list_files(path): List files and directories in a directory
- read_file(path): Read the contents of a file

Process:
1. Use list_files to discover wiki files if you're not sure where to look
2. Use read_file to read relevant wiki sections and find the answer
3. Include the source reference in your answer (format: wiki/filename.md#section-anchor)

Guidelines:
- Only make necessary tool calls - don't over-use tools
- If you know the answer directly, you can respond without using tools
- Always provide a source reference with your answer when you use tools
- The source should be in format: wiki/filename.md#section-name

When providing a source reference:
- Use the file path (e.g., wiki/git-workflow.md)
- Add a section anchor if applicable (e.g., #resolving-merge-conflicts)
- Format: wiki/filename.md#section-name
"""


# === Agentic Loop ===

MAX_TOOL_CALLS = 10


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Execute a tool and return the result."""
    if tool_name not in TOOLS:
        return f"Error: Unknown tool: {tool_name}"

    try:
        func = TOOLS[tool_name]
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
            answer = message.get("content", "")
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
            result = execute_tool(tool_name, tool_args)

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
                if path_arg.startswith("wiki/"):
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
