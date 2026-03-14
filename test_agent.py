"""Regression tests for agent.py CLI - Task 2 (Documentation Agent)."""

import json
import subprocess
from pathlib import Path


def test_agent_merge_conflict_question() -> None:
    """Test that agent uses read_file for merge conflict question."""
    project_root = Path(__file__).parent
    agent_path = project_root / "agent.py"

    # Run agent with merge conflict question
    result = subprocess.run(
        ["uv", "run", str(agent_path), "How do you resolve a merge conflict?"],
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

    # Check that read_file was used
    tools_used = [call["tool"] for call in output["tool_calls"]]
    assert "read_file" in tools_used, "Expected read_file to be called"

    # Check source references wiki/git*.md
    source = output["source"]
    assert source.startswith("wiki/"), (
        f"Source should start with 'wiki/', got: {source}"
    )
    assert source.endswith(".md"), f"Source should end with '.md', got: {source}"


def test_agent_list_files_question() -> None:
    """Test that agent uses list_files for wiki listing question."""
    project_root = Path(__file__).parent
    agent_path = project_root / "agent.py"

    # Run agent with list files question
    result = subprocess.run(
        ["uv", "run", str(agent_path), "What files are in the wiki?"],
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

    # Check that list_files was used
    tools_used = [call["tool"] for call in output["tool_calls"]]
    assert "list_files" in tools_used, "Expected list_files to be called"

    # Check answer mentions wiki files
    answer = output["answer"].lower()
    assert "wiki" in answer or len(output["tool_calls"]) > 0, (
        "Answer should reference wiki"
    )
