# Agent Architecture

## Overview

`agent.py` is a CLI tool that implements an **agentic loop** with tools to answer questions using the project wiki. The agent can:

1. Call an LLM (Qwen Code API) with tool definitions
2. Execute tools (`read_file`, `list_files`) based on LLM decisions
3. Feed tool results back to the LLM
4. Iterate until a final answer is produced

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Agentic Loop                                  │
│                                                                   │
│  ┌─────────┐     ┌─────────────┐     ┌──────────┐               │
│  │  User   │────▶│  LLM +      │────▶│  Tools   │               │
│  │ Question│     │  Tools      │     │ Execute  │               │
│  └─────────┘     └─────────────┘     └──────────┘               │
│       ▲               │  │                    │                  │
│       │               │  │                    │                  │
│       │         ┌─────┘  └─────┐              │                  │
│       │         │              │              │                  │
│       │    ┌────▼────┐   ┌────▼────┐         │                  │
│       │    │  Tool   │   │  Final  │         │                  │
│       │    │  Calls  │   │ Answer  │◀────────┘                  │
│       │    └─────────┘   └─────────┘                            │
│       │         │                                               │
│       └─────────┴───────────────────────────────────────────────┘
│                 │
│                 ▼
│        (loop back to LLM with tool results)
└──────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Configuration (`AgentSettings`)

- Loads environment variables from `.env.agent.secret`
- Required fields:
  - `LLM_API_KEY`: API key for authentication
  - `LLM_API_BASE`: Base URL of the LLM API endpoint
  - `LLM_MODEL`: Model name (default: `qwen3-coder-plus`)

### 2. Tools

#### `read_file(path: str) -> str`

Read the contents of a file from the project repository.

**Parameters:**

- `path`: Relative path from project root (e.g., `wiki/git-workflow.md`)

**Security:**

- Validates path does not contain `..` (directory traversal prevention)
- Ensures resolved path is within project directory
- Returns error message if file doesn't exist

#### `list_files(path: str) -> str`

List files and directories at a given path.

**Parameters:**

- `path`: Relative directory path from project root (e.g., `wiki`)

**Security:**

- Validates path does not contain `..`
- Ensures resolved path is within project directory
- Returns newline-separated listing

### 3. Tool Schemas

Tools are registered with the LLM using OpenAI-compatible function schemas:

```python
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
                    "description": "Relative path from project root"
                }
            },
            "required": ["path"]
        }
    }
}
```

### 4. Agentic Loop

The loop executes as follows:

1. **Send request**: User question + system prompt + tool schemas to LLM
2. **Check response**:
   - If `tool_calls` present → execute each tool, append results as `tool` role messages
   - If text message only → extract answer and return
3. **Repeat**: Feed tool results back to LLM and continue
4. **Max iterations**: Stop after 10 tool calls

**Message history format:**

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "content": result, "tool_call_id": "..."},
    # ... loop continues ...
]
```

### 5. System Prompt

The system prompt instructs the LLM to:

- Use `list_files` to discover wiki files when unsure
- Use `read_file` to read relevant sections
- Include source references in the answer (format: `wiki/filename.md#section-anchor`)
- Only make necessary tool calls

### 6. Output Format

```json
{
    "answer": "The answer text with explanation",
    "source": "wiki/git-workflow.md#resolving-merge-conflicts",
    "tool_calls": [
        {
            "tool": "list_files",
            "args": {"path": "wiki"},
            "result": "git-workflow.md\ngit.md\n..."
        },
        {
            "tool": "read_file",
            "args": {"path": "wiki/git-workflow.md"},
            "result": "# Git workflow..."
        }
    ]
}
```

**Fields:**

- `answer`: The LLM's final answer
- `source`: Wiki file reference (extracted from files read)
- `tool_calls`: Array of all tool calls with args and results

## LLM Provider

- **Provider**: Qwen Code API (self-hosted via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus` (supports function calling)
- **API Format**: OpenAI-compatible chat completions with tool calling

## Usage

```bash
# Basic usage
uv run agent.py "How do you resolve a merge conflict?"

# Output (stdout)
{
  "answer": "...",
  "source": "wiki/git.md#merge-conflict",
  "tool_calls": [...]
}
```

## Environment Setup

1. Copy the example environment file:

   ```bash
   cp .env.agent.example .env.agent.secret
   ```

2. Edit `.env.agent.secret` with your credentials:

   ```
   LLM_API_KEY=your-api-key
   LLM_API_BASE=http://<vm-ip>:<port>/v1
   LLM_MODEL=qwen3-coder-plus
   ```

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing CLI argument | Prints usage to stderr, exits with code 1 |
| Missing `.env.agent.secret` | Prints error to stderr, exits with code 1 |
| Path traversal attempt | Returns error to LLM (tool result) |
| File not found | Returns error to LLM (tool result) |
| Max tool calls reached | Outputs partial answer with warning |
| HTTP timeout (>60s) | Prints timeout error to stderr, exits with code 1 |
| HTTP error | Prints status code to stderr, exits with code 1 |

## Security

**Path validation:**

- All tool paths are validated to prevent directory traversal (`..`)
- Resolved paths must be within the project root directory
- Tools return error messages (not file contents) for invalid paths

## Testing

Run the regression tests:

```bash
pytest test_agent.py -v
pytest backend/tests/unit/test_agent.py -v
```

Tests verify:

- Agent outputs valid JSON
- `answer`, `source`, and `tool_calls` fields are present
- Tools are used correctly for specific questions

## Dependencies

- `httpx`: HTTP client for API requests
- `python-dotenv`: Environment variable loading
- `pydantic`: Configuration validation

## Future Extensions (Task 3)

- Add more tools (e.g., `query_api` for backend queries)
- Enhanced source extraction (section anchors)
- Better error recovery in agentic loop
