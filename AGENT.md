# Agent Architecture

## Overview

`agent.py` is a CLI tool that implements an **agentic loop** with tools to answer questions using:

1. Project wiki documentation
2. Source code files
3. Live backend API queries

The agent can call an LLM (Qwen Code API) with tool definitions, execute tools based on LLM decisions, feed tool results back, and iterate until a final answer is produced.

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

Loads environment variables from multiple sources:

| Variable | Source File | Purpose |
|----------|-------------|---------|
| `LLM_API_KEY` | `.env.agent.secret` | LLM provider API key |
| `LLM_API_BASE` | `.env.agent.secret` | LLM API endpoint URL |
| `LLM_MODEL` | `.env.agent.secret` | Model name (default: `qwen3-coder-plus`) |
| `LMS_API_KEY` | `.env.docker.secret` | Backend API key for `query_api` auth |
| `AGENT_API_BASE_URL` | Environment | Backend API URL (default: `http://localhost:42002`) |

**Important:** Two distinct keys:

- `LMS_API_KEY` (in `.env.docker.secret`) - protects backend endpoints
- `LLM_API_KEY` (in `.env.agent.secret`) - authenticates with LLM provider

### 2. Tools

#### `read_file(path: str) -> str`

Read the contents of a file from the project repository.

**Parameters:**

- `path`: Relative path from project root (e.g., `wiki/git-workflow.md`, `backend/app/routers/items.py`)

**Security:**

- Validates path does not contain `..` (directory traversal prevention)
- Ensures resolved path is within project directory
- Returns error message if file doesn't exist

#### `list_files(path: str) -> str`

List files and directories at a given path.

**Parameters:**

- `path`: Relative directory path from project root (e.g., `wiki`, `backend/app/routers`)

**Security:**

- Validates path does not contain `..`
- Ensures resolved path is within project directory
- Returns newline-separated listing

#### `query_api(method: str, path: str, body: str | None = None) -> str`

Call the backend API with LMS_API_KEY authentication.

**Parameters:**

- `method`: HTTP method (GET, POST, PUT, DELETE, PATCH)
- `path`: API path (e.g., `/items/`, `/analytics/completion-rate`)
- `body`: Optional JSON request body (for POST/PUT/PATCH)

**Returns:** JSON string with `status_code` and `body`

**Authentication:**

- Uses `LMS_API_KEY` from `.env.docker.secret`
- Sends as `Authorization: Bearer <LMS_API_KEY>` header
- Returns error if key not configured

### 3. Tool Schemas

Tools are registered with the LLM using OpenAI-compatible function schemas. Each schema includes:

- Tool name and description
- Parameter types and descriptions
- Required parameters
- Enum constraints (for `method` in `query_api`)

### 4. Agentic Loop

The loop executes as follows:

1. **Send request**: User question + system prompt + tool schemas to LLM
2. **Check response**:
   - If `tool_calls` present → execute each tool, append results as `tool` role messages
   - If text message only → extract answer and return
3. **Repeat**: Feed tool results back to LLM and continue
4. **Max iterations**: Stop after 15 tool calls

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

The system prompt guides the LLM on:

**Tool selection:**

- Use `list_files`/`read_file` for: wiki documentation, source code, configuration files
- Use `query_api` for: live data (item counts, scores), API behavior (status codes), testing endpoints

**Process:**

1. Wiki questions → `list_files` to discover, `read_file` to find answer
2. Source code questions → `read_file` on `backend/` files
3. Live data questions → `query_api` to query running API
4. Bug diagnosis → `query_api` to see error, then `read_file` to examine source

**Answer guidelines:**

- Always give complete, final answers
- Never say "let me check" without completing the thought
- Provide source references when using `read_file`
- Mention endpoint queried when using `query_api`

**API authentication knowledge:**

- Backend API requires Bearer token authentication
- Unauthenticated requests typically return 401/403

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
        },
        {
            "tool": "query_api",
            "args": {"method": "GET", "path": "/items/"},
            "result": "{\"status_code\": 200, \"body\": \"[...]\"}"
        }
    ]
}
```

**Fields:**

- `answer`: The LLM's final answer (required)
- `source`: Wiki/file reference (optional for `query_api` results)
- `tool_calls`: Array of all tool calls with args and results (required)

## LLM Provider

- **Provider**: Qwen Code API (self-hosted via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus` (supports function calling)
- **API Format**: OpenAI-compatible chat completions with tool calling

## Usage

```bash
# Wiki question
uv run agent.py "How do you resolve a merge conflict?"

# Source code question
uv run agent.py "What framework does the backend use?"

# Live data question
uv run agent.py "How many items are in the database?"

# API behavior question
uv run agent.py "What status code for unauthenticated request?"
```

## Environment Setup

1. Copy environment files:

   ```bash
   cp .env.agent.example .env.agent.secret
   cp .env.docker.example .env.docker.secret
   ```

2. Edit `.env.agent.secret`:

   ```
   LLM_API_KEY=your-llm-api-key
   LLM_API_BASE=http://<vm-ip>:<port>/v1
   LLM_MODEL=qwen3-coder-plus
   ```

3. Edit `.env.docker.secret`:

   ```
   LMS_API_KEY=your-backend-api-key
   ```

## Error Handling

| Error | Handling |
|-------|----------|
| Missing CLI argument | Prints usage to stderr, exits with code 1 |
| Missing env files | Prints error to stderr, exits with code 1 |
| Path traversal attempt | Returns error to LLM (tool result) |
| File not found | Returns error to LLM (tool result) |
| Missing LMS_API_KEY | Returns error to LLM for `query_api` |
| API connection error | Returns error to LLM with details |
| HTTP error (4xx/5xx) | Returns status_code and error body to LLM |
| Max tool calls reached | Outputs partial answer with warning |
| LLM timeout (>60s) | Prints timeout error to stderr, exits with code 1 |

## Security

**Path validation:**

- All tool paths are validated to prevent directory traversal (`..`)
- Resolved paths must be within project root directory
- Tools return error messages (not file contents) for invalid paths

**API authentication:**

- `LMS_API_KEY` loaded from environment (not hardcoded)
- `.env.docker.secret` is gitignored
- API handles its own authorization

## Testing

Run the regression tests:

```bash
pytest test_agent.py -v              # Task 2 tests
pytest test_agent_task3.py -v        # Task 3 tests
```

Tests verify:

- Agent outputs valid JSON
- `answer`, `source`, and `tool_calls` fields are present
- Correct tools are used for specific question types
- `read_file` for wiki/source questions
- `query_api` for live data questions

## Benchmark Performance

**Local evaluation (`run_eval.py`):** 8/10 questions passed

**Passing questions:**

1. Wiki: Protect a branch on GitHub ✓
2. Wiki: SSH to VM ✓
3. Source: Web framework (FastAPI) ✓
4. Source: API routers (intermittent) ~
5. Data: Items in database ✓
6. API: Status code without auth ✓
7. Bug: `/analytics/completion-rate` ZeroDivisionError ✓
8. Bug: `/analytics/top-learners` TypeError ✓

**Borderline questions:**

- Question 4 (API routers): LLM sometimes stops early
- Question 9 (Request lifecycle): Complex multi-file reasoning, LLM may produce incomplete answer

**Notes:**

- LLM behavior is somewhat non-deterministic
- Same question may pass or fail depending on model output
- For production use, would need retry logic for incomplete answers

## Lessons Learned

1. **Tool descriptions matter**: Vague descriptions lead to wrong tool usage. Be specific about when to use each tool.

2. **System prompt is crucial**: The LLM needs explicit guidance on tool selection, especially for distinguishing between wiki lookup vs. API queries.

3. **LLM non-determinism**: The same question can produce different results. The LLM sometimes produces incomplete answers ("Let me check...") without finishing the thought.

4. **Max iterations**: Started with 10, increased to 15 to allow more complex multi-file analysis.

5. **Source tracking**: Initially only tracked `wiki/` files, but needed to extend to `backend/` files and configuration files for proper attribution.

6. **Authentication knowledge**: The LLM can infer that unauthenticated requests return 401/403 without actually testing (which would require a special "no-auth" mode).

7. **Answer completeness**: Added explicit instructions to "give complete answers" and "don't leave answers hanging" to reduce incomplete responses.

8. **Environment separation**: Keeping LLM credentials (`LLM_API_KEY`) separate from backend credentials (`LMS_API_KEY`) is important for security and flexibility.

## Dependencies

- `httpx`: HTTP client for API requests
- `python-dotenv`: Environment variable loading from multiple files
- `pydantic`: Configuration validation

## Future Extensions

- Add retry logic for incomplete answers
- Implement "no-auth" mode for `query_api` to test authentication behavior
- Add more tools (e.g., `search_code` for grep-like functionality)
- Improve source extraction (section anchors from markdown headings)
- Add conversation memory for multi-turn interactions
