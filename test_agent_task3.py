"""Regression tests for agent.py CLI - Task 3 (System Agent)."""

import json
import subprocess
from pathlib import Path


def test_agent_framework_question() -> None:
    """Test that agent uses read_file for framework question."""
    project_root = Path(__file__).parent
    agent_path = project_root / "agent.py"

    # Run agent with framework question
    result = subprocess.run(
        ["uv", "run", str(agent_path), "What framework does the backend use?"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=120,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(f"Invalid JSON output: {result.stdout}") from e

    # Check required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "source" in output, "Missing 'source' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"

    # Check that read_file was used (to read source code)
    tools_used = [call["tool"] for call in output["tool_calls"]]
    assert "read_file" in tools_used, "Expected read_file to be called"

    # Check answer mentions FastAPI
    answer = output["answer"].lower()
    assert "fastapi" in answer, f"Answer should mention FastAPI, got: {answer[:100]}"


def test_agent_items_count_question() -> None:
    """Test that agent uses query_api for database count question."""
    project_root = Path(__file__).parent
    agent_path = project_root / "agent.py"

    # Run agent with items count question
    result = subprocess.run(
        ["uv", "run", str(agent_path), "How many items are in the database?"],
        capture_output=True,
        text=True,
        cwd=project_root,
        timeout=120,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise AssertionError(f"Invalid JSON output: {result.stdout}") from e

    # Check required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"

    # Check that query_api was used
    tools_used = [call["tool"] for call in output["tool_calls"]]
    assert "query_api" in tools_used, "Expected query_api to be called"

    # Check answer contains a number
    answer = output["answer"]
    import re
    numbers = re.findall(r"\d+", answer)
    assert len(numbers) > 0, f"Answer should contain a number, got: {answer[:100]}"
