# Task 3: The System Agent

## Overview

Add a `query_api` tool to the documentation agent so it can query the deployed backend API. This enables the agent to answer:

1. **Static system facts** - framework, ports, status codes (from source code)
2. **Data-dependent queries** - item count, scores, analytics (from live API)

## LLM Provider & Model

- **Provider**: Qwen Code API (self-hosted via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus` (supports function calling)

## Environment Variables

The agent must read configuration from environment variables (not hardcoded):

| Variable | Purpose | Source File |
|----------|---------|-------------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` (optional) | Environment, defaults to `http://localhost:42002` |

**Important:** Two distinct keys:

- `LMS_API_KEY` (in `.env.docker.secret`) - protects backend endpoints
- `LLM_API_KEY` (in `.env.agent.secret`) - authenticates with LLM provider

## New Tool: `query_api`

Call the deployed backend API with authentication.

### Schema

```json
{
    "type": "function",
    "function": {
        "name": "query_api",
        "description": "Call the backend API and return the response",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
                },
                "path": {
                    "type": "string",
                    "description": "API path (e.g., '/items/', '/analytics/completion-rate')"
                },
                "body": {
                    "type": "string",
                    "description": "Optional JSON request body (for POST/PUT/PATCH)"
                }
            },
            "required": ["method", "path"]
        }
    }
}
```

### Implementation

```python
def tool_query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend API with LMS_API_KEY authentication."""
    import os
    
    api_key = os.environ.get("LMS_API_KEY")
    base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")
    
    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    # Make HTTP request
    # Return JSON string with status_code and body
```

### Authentication

- Use `LMS_API_KEY` from `.env.docker.secret`
- Send as `Authorization: Bearer <LMS_API_KEY>` header
- Load at runtime from environment (not hardcoded)

## Updated System Prompt

The system prompt should guide the LLM on **when to use which tool**:

```
You are a documentation and system agent that answers questions using:
1. Project wiki (via list_files and read_file)
2. Source code (via read_file)
3. Live backend API (via query_api)

Tool selection guide:
- Use list_files/read_file for: wiki documentation, source code, configuration files
- Use query_api for: live data (item counts, scores), API behavior (status codes), 
  testing endpoints, checking analytics

When answering:
1. For wiki questions → use read_file on wiki/ files
2. For source code questions → use read_file on backend/ files
3. For live data questions → use query_api to query the running API
4. For API behavior questions → use query_api to test endpoints

Always provide a source reference when using read_file (format: path/to/file.md#section).
For query_api results, mention the endpoint queried.
```

## Output Format Changes

**Task 3 update:** `source` is now **optional** (system questions may not have a wiki source).

```json
{
    "answer": "There are 120 items in the database.",
    "source": "",  // Optional - can be empty for query_api results
    "tool_calls": [
        {
            "tool": "query_api",
            "args": {"method": "GET", "path": "/items/"},
            "result": "{\"status_code\": 200, \"body\": {...}}"
        }
    ]
}
```

## Agentic Loop

The loop remains the same as Task 2:

1. Send question + tools to LLM
2. If tool_calls → execute, feed back, repeat
3. If final answer → return
4. Max 10 tool calls

## Benchmark Questions

The autochecker runs 10 local questions (+ hidden questions):

| # | Question | Grading | Expected Tools |
|---|----------|---------|----------------|
| 0 | Wiki: protect a branch | keyword | read_file |
| 1 | Wiki: SSH to VM | keyword | read_file |
| 2 | Source: web framework | keyword | read_file |
| 3 | Source: API routers | keyword | list_files |
| 4 | Data: items in database | keyword | query_api |
| 5 | API: status code without auth | keyword | query_api |
| 6 | Bug: /analytics/completion-rate | keyword | query_api, read_file |
| 7 | Bug: /analytics/top-learners | keyword | query_api, read_file |
| 8 | Reasoning: request lifecycle | LLM judge | read_file |
| 9 | Reasoning: ETL idempotency | LLM judge | read_file |

## Implementation Steps

1. **Add `query_api` tool function**
   - Load `LMS_API_KEY` from environment
   - Load `AGENT_API_BASE_URL` (default: `http://localhost:42002`)
   - Make HTTP request with authentication
   - Return JSON string with `status_code` and `body`

2. **Add `query_api` schema**
   - Register alongside existing tools
   - Include method, path, body parameters

3. **Update system prompt**
   - Guide LLM on tool selection
   - Clarify when to use wiki vs API

4. **Make `source` optional**
   - Update output format
   - Update tests to allow empty source

5. **Test with `run_eval.py`**
   - Run benchmark locally
   - Iterate on failures
   - Improve tool descriptions as needed

## Error Handling

| Error | Handling |
|-------|----------|
| Missing `LMS_API_KEY` | Return error to LLM: "Missing LMS_API_KEY" |
| API connection error | Return error to LLM with details |
| HTTP error (4xx/5xx) | Return status_code and error body to LLM |
| Timeout | Return timeout error to LLM |

## Security

- `LMS_API_KEY` loaded from environment (not hardcoded)
- `.env.docker.secret` is gitignored
- No path validation needed for API calls (API handles its own security)

## Testing

Add 2 regression tests:

1. **"What framework does the backend use?"** → expects `read_file` on source code
2. **"How many items are in the database?"** → expects `query_api` call

## Iteration Strategy

1. Run `uv run run_eval.py` to see initial score
2. For each failure:
   - Check if wrong tool was used → improve system prompt
   - Check if tool returned error → fix tool implementation
   - Check if answer format wrong → adjust prompt
3. Re-run until all 10 questions pass
4. Document lessons learned in AGENT.md

## Benchmark Results

### Initial Run

**Score: 3/10 passed**

**Failures:**

- Question 4: "List all API router modules..." - Agent started examining but didn't complete.

### After Fixes

**Best Score: 8/10 passed**

**Remaining Failures:**

- Question 4 (intermittent): LLM sometimes stops early with "Let me continue checking..."
- Question 9: LLM produces incomplete answer ("Let me check...") for complex multi-file reasoning

**Diagnosis:**

- The agent needs to complete the full loop of list_files → read multiple files → synthesize answer
- LLM sometimes produces incomplete answers due to non-deterministic behavior
- Increased MAX_TOOL_CALLS from 10 to 15 to allow more iterations
- Updated system prompt to emphasize complete answers
- LLM behavior is somewhat non-deterministic - same question may pass or fail

## Dependencies

- No new dependencies needed (already have `httpx`)
