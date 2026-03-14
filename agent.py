#!/usr/bin/env python3
"""
Agent CLI - Calls an LLM and returns structured JSON output.

Usage:
    uv run agent.py "Your question here"

Output:
    {"answer": "...", "tool_calls": []}
"""

import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel


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

    # Load environment variables from file
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


def call_lllm(question: str, settings: AgentSettings) -> str:
    """Send question to LLM and return the answer."""
    url = f"{settings.llm_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": question}],
    }

    print(f"Sending request to {url}", file=sys.stderr)
    print(f"Model: {settings.llm_model}", file=sys.stderr)

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract answer from response
            answer = data["choices"][0]["message"]["content"]
            return answer

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


def main() -> None:
    """Main entry point."""
    # Parse command-line argument
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    # Load configuration
    settings = load_settings()

    # Call LLM and get answer
    answer = call_lllm(question, settings)

    # Output structured JSON
    output = {"answer": answer, "tool_calls": []}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
