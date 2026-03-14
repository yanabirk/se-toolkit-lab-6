# Task 2: The Documentation Agent

## Overview

Build an agentic loop that allows the LLM to use tools (`read_file`, `list_files`) to navigate the project wiki and find answers to questions.

## LLM Provider & Model

- **Provider**: Qwen Code API (self-hosted via qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus` (supports function calling)
- **API Format**: OpenAI-compatible chat completions with tool calling

## Tool Definitions

### 1. `read_file`

Read a file from the project repository.

**Schema:**
```json
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
          "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
        }
      },
      "required": ["path"]
    }
  }
}
```

**Security:**
- Validate path does not contain `..` (directory traversal)
- Ensure resolved path is within project directory
- Return error message if file doesn't exist or is outside bounds

### 2. `list_files`

List files and directories at a given path.

**Schema:**
```json
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
          "description": "Relative directory path from project root (e.g., 'wiki')"
        }
      },
      "required": ["path"]
    }
  }
}
```

**Security:**
- Validate path does not contain `..`
- Ensure resolved path is within project directory
- Return error message if directory doesn't exist or is outside bounds

## Agentic Loop Architecture

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

### Loop Flow

1. **Initial Request**: Send user question + system prompt + tool definitions to LLM
2. **Check Response**:
   - If `tool_calls` present → execute each tool, append results as `tool` role messages, go to step 1
   - If text message (no tool calls) → extract answer, output JSON and exit
3. **Max Iterations**: Stop after 10 tool calls, use whatever answer is available

### Message History Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_question},
    # After tool calls:
    # {"role": "assistant", "tool_calls": [...]},
    # {"role": "tool", "content": tool_result, "tool_call_id": "..."},
    # ... loop continues ...
]
```

## System Prompt Strategy

The system prompt should instruct the LLM to:

1. Use `list_files` to discover wiki files when unsure where to look
2. Use `read_file` to read relevant wiki sections
3. Include source references in the final answer (file path + section anchor)
4. Only make necessary tool calls (don't over-use tools)
5. Provide a final answer even if uncertain

Example system prompt:
```
You are a documentation agent that answers questions using the project wiki.

Tools available:
- list_files(path): List files in a directory
- read_file(path): Read a file's contents

Process:
1. Use list_files to discover wiki files if needed
2. Use read_file to find the answer
3. Include the source reference (e.g., wiki/git-workflow.md#section-name)

Always provide a source reference with your answer.
```

## Output Format

```json
{
  "answer": "The answer text",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

## Implementation Components

### 1. Tool Functions
- `tool_read_file(path: str) -> str`: Read file with security validation
- `tool_list_files(path: str) -> str`: List directory with security validation
- `validate_path(path: str) -> Path`: Validate and resolve path safely

### 2. Tool Schemas
- Define OpenAI-compatible function schemas for both tools
- Register in LLM API request

### 3. Agentic Loop
- Track tool call count (max 10)
- Maintain message history
- Execute tools and feed results back
- Extract final answer from LLM response

### 4. Output Formatting
- Track all tool calls with args and results
- Extract source from answer or infer from files read
- Build JSON output

## Error Handling

| Error | Handling |
|-------|----------|
| Path traversal attempt | Return error message to LLM |
| File not found | Return error message to LLM |
| Max tool calls reached | Output partial answer with warning |
| LLM error | Exit with error to stderr |

## Dependencies

- Existing: `httpx`, `python-dotenv`, `pydantic`
- No new dependencies needed

## Testing

Two regression tests:

1. **"How do you resolve a merge conflict?"**
   - Expected: `read_file` in tool_calls
   - Expected: `wiki/git-workflow.md` in source

2. **"What files are in the wiki?"**
   - Expected: `list_files` in tool_calls
   - Expected: list of wiki files in answer
