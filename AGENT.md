# Agent Architecture

## Overview

`agent.py` is a CLI tool that connects to an LLM (Large Language Model) and returns structured JSON responses. It serves as the foundation for the agentic system that will be extended in subsequent tasks.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Command Line   │────▶│   agent.py      │────▶│   LLM API       │
│  (question)     │     │                 │     │   (Qwen Code)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │  JSON Output    │
                        │  {answer,       │
                        │   tool_calls}   │
                        └─────────────────┘
```

## Components

### 1. Configuration (`AgentSettings`)

- Loads environment variables from `.env.agent.secret`
- Required fields:
  - `LLM_API_KEY`: API key for authentication
  - `LLM_API_BASE`: Base URL of the LLM API endpoint
  - `LLM_MODEL`: Model name (default: `qwen3-coder-plus`)

### 2. LLM Client (`call_llm`)

- Uses `httpx` for HTTP requests
- Sends POST request to `{LLM_API_BASE}/chat/completions`
- OpenAI-compatible API format
- 60-second timeout
- Error handling for timeouts and HTTP errors

### 3. CLI Interface (`main`)

- Parses question from command-line argument
- Validates input
- Outputs JSON to stdout
- All debug/error messages to stderr

## LLM Provider

- **Provider**: Qwen Code API (self-hosted via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus`
- **API Format**: OpenAI-compatible chat completions API

## Usage

```bash
# Basic usage
uv run agent.py "What does REST stand for?"

# Output (stdout)
{"answer": "REST stands for **Representational State Transfer**.", "tool_calls": []}
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

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "The LLM's response text",
  "tool_calls": []
}
```

- `answer`: The text response from the LLM
- `tool_calls`: Empty array (will be populated in Task 2 when tools are added)

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing CLI argument | Prints usage to stderr, exits with code 1 |
| Missing `.env.agent.secret` | Prints error to stderr, exits with code 1 |
| Missing environment variables | Prints error to stderr, exits with code 1 |
| HTTP timeout (>60s) | Prints timeout error to stderr, exits with code 1 |
| HTTP error | Prints status code and response to stderr, exits with code 1 |

## Dependencies

- `httpx`: HTTP client for API requests
- `python-dotenv`: Environment variable loading
- `pydantic`: Configuration validation

## Testing

Run the regression test:

```bash
pytest backend/tests/unit/test_agent.py
```

The test verifies:
- Agent runs successfully
- Output is valid JSON
- `answer` field is present
- `tool_calls` field is present

## Future Extensions (Tasks 2-3)

- **Task 2**: Add tool support (file operations, API queries)
- **Task 3**: Add agentic loop with tool selection and execution
