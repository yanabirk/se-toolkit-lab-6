# Task 1: Call an LLM from Code

## LLM Provider & Model

- **Provider**: Qwen Code API (self-hosted on VM via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus`
- **API Format**: OpenAI-compatible chat completions API

## Environment Configuration

The agent reads configuration from `.env.agent.secret`:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for Qwen Code | from `~/qwen-code-oai-proxy/.env` |
| `LLM_API_BASE` | API base URL | `http://<vm-ip>:<port>/v1` |
| `LLM_MODEL` | Model name | `qwen3-coder-plus` |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  CLI Args   │────▶│  agent.py   │────▶│  HTTP POST  │────▶│  LLM API    │
│  (question) │     │             │     │  /v1/chat   │     │  (Qwen)     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Parse JSON │
                    │  Response   │
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Output     │
                    │  {answer,   │
                    │  tool_calls}│
                    └─────────────┘
```

## Implementation Components

### 1. Configuration Loading
- Use `pydantic-settings` to load `.env.agent.secret`
- Validate required fields: `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`

### 2. CLI Argument Parsing
- Use `sys.argv` to get the question from first command-line argument
- Exit with error to stderr if no argument provided

### 3. LLM API Call
- Use `httpx` (sync client) for HTTP request
- POST to `{LLM_API_BASE}/chat/completions`
- Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
- Body: `{"model": LLM_MODEL, "messages": [{"role": "user", "content": question}]}`
- Timeout: 60 seconds

### 4. Response Parsing
- Extract `choices[0].message.content` from LLM response
- Build output: `{"answer": "<content>", "tool_calls": []}`

### 5. Output
- **stdout**: Single JSON line (valid JSON only)
- **stderr**: All debug/error messages
- **Exit code**: 0 on success, non-zero on error

## Error Handling

| Error | Handling |
|-------|----------|
| Missing CLI argument | Print usage to stderr, exit 1 |
| Missing env file or vars | Print error to stderr, exit 1 |
| HTTP error / timeout | Print error to stderr, exit 1 |
| Invalid LLM response | Print error to stderr, exit 1 |

## Testing

- 1 regression test: run `agent.py` as subprocess, verify JSON output has `answer` and `tool_calls` fields

## Dependencies

- `httpx` (already in project) - HTTP client
- `pydantic-settings` (already in project) - env var loading
- Standard library: `sys`, `json`
