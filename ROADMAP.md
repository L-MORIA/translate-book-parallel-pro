# Roadmap — universal agent support

## Goal

One pipeline, any agent: OpenCode, Hermes, Claude Code, Codex, ZCode, MiniMax
Code, Kimi, Cursor, plain CI. No forks of the translation logic, no duplicated
prompt files, no per-host copy of the pipeline.

## Current state (v1.3.0)

- The core is portable: `scripts/*.py` is plain Python; prompts, glossary,
  manifest, run_state and meta schemas are host-independent.
- `AGENT_ADAPTER.md` documents the capability contract, the four host-specific
  points (install path, sub-agent primitive, concurrency cap, interpreter) and
  the sequential fallback for hosts without sub-agents.
- OpenCode was verified end-to-end: `sleepy-hollow` → Russian, 17 chunks, 17
  isolated `general` sub-agents, DOCX/EPUB/PDF built.
- UTF-8 CLI output is enforced by `scripts/_stdio.py`; the cp1251 crash in
  `glossary.py print-terms-for-chunk` is fixed, and the missing-glossary crash
  is fixed too (v1.2.17).
- **MCP server MVP shipped (v1.3.0)**: `python scripts/mcp_server.py
  --workspace ROOT` serves all eight P0 tools over stdio with the standard
  library only — no MCP SDK dependency (open question 1 resolved in favor of
  stdlib JSON-RPC; the used surface — initialize/ping/tools/resources/prompts
  — is small and stable). M1–M3 done; M4 (packaging) and M5 (HTTP) remain.

The remaining problem is integration, not translation. Every host still needs
its own glue: a skill file, a sub-agent call, a batch size. The roadmap removes
that glue.

## Design principles

1. The pipeline stays pure Python and keeps working offline.
2. No mandatory API key: by default the host LLM does the translation.
3. Hermes remains supported; no breaking changes to `SKILL.md` contracts.
4. State lives in the temp directory, so every integration is resumable.
5. New integrations must be testable without a real LLM (fixtures + mocks).

## P0 — MCP server (chosen path)

**Why:** MCP is the common integration layer for OpenCode, Claude Code, Codex,
Cursor and most modern agents. One server works everywhere and does not depend
on a host's skill format or sub-agent API. It is the only option that makes the
pipeline genuinely host-agnostic without duplicating the LLM client.

### Target architecture

```
scripts/mcp_server.py        # thin stdio/HTTP entry point
translate_book_mcp/
  server.py                  # tool/resource registration
  tools.py                   # convert / plan / prompt / submit / build
  paths.py                   # workspace confinement and validation
  prompts.py                 # translation prompt templates
```

The server is stateless: every call receives a `temp_dir` and reads/writes the
same files the CLI uses. This keeps CLI and MCP behavior identical.

### MCP tools (MVP)

| Tool | Purpose | Returns |
|---|---|---|
| `convert_book` | PDF/DOCX/EPUB → chunks | `temp_dir`, `chunk_count`, metadata |
| `get_status` | manifest + run_state + glossary snapshot | counts, missing outputs, errors |
| `get_translation_plan` | which chunks need work | `translation_chunk_ids`, `record_only_chunk_ids`, `unchanged_chunk_ids` |
| `get_chunk_prompt` | full prompt for one chunk | prompt text, source/output/meta paths, term table, neighbor context |
| `submit_translation` | write `output_chunkNNNN.md` + meta | validation result (UTF-8, non-empty, hash) |
| `merge_meta` | prepare/apply glossary merge | `auto_apply`, `decisions_needed`, summary |
| `build_book` | merge → HTML → DOCX/EPUB/PDF | output paths and sizes |
| `validate_book` | manifest/chunk-set validation | errors, warnings |

`get_chunk_prompt` is the key tool: the host agent can either translate the
returned prompt itself or spawn its own sub-agents with it. The server never
calls an LLM, so it works with any model and any provider.

### MCP resources

- `translate-book://temp/{temp_id}/glossary`
- `translate-book://temp/{temp_id}/manifest`
- `translate-book://temp/{temp_id}/chunks/{chunk_id}`
- `translate-book://temp/{temp_id}/output/{chunk_id}`

Large content stays on disk; tools exchange paths and small JSON, not whole
books over JSON-RPC.

### MCP prompts

- `translate_chunk` — the host's `/` command can inject the translation prompt
  with `temp_dir`, `chunk_id`, `target_language` arguments.
- `review_translation` — optional quality-check prompt.

### Transport and security

- **stdio** first: local agents start the server automatically.
- **Streamable HTTP** later: remote/multi-client use, with auth.
- Confine all paths to configured workspace roots; reject `..`, symlink escapes
  and absolute paths outside the root.
- Never accept shell strings; reuse the existing list-argv subprocess calls.
- Limit payload sizes and redact keys from errors/logs.
- Windows path/encoding behavior is already covered by `_stdio.py`; add MCP
  tests for backslashes and non-ASCII paths.

### Milestones

- **M1 — read-only: ✅ v1.3.0** `convert_book`, `get_status`,
  `get_translation_plan`, `get_chunk_prompt`, resources. Verified with a
  subprocess-level end-to-end test (initialize → tools → submit → validate).
- **M2 — write path: ✅ v1.3.0** `submit_translation`, `merge_meta`,
  `validate_book`.
- **M3 — build: ✅ v1.3.0** `build_book`, format results.
- **M4 — packaging:** `translate-book-mcp` console entry point, config example,
  Docker image with Calibre + pandoc.
- **M5 — HTTP:** streamable HTTP transport, auth, multi-client tests.

### Acceptance criteria

- OpenCode, Claude Code and one generic MCP client translate the
  `sleepy-hollow` baseline to Russian with **zero repo edits**.
- The output files, manifest hashes and format sizes match the CLI run.
- Every MCP tool has unit tests; an integration test uses prewritten chunk
  outputs (no LLM required).
- The server starts in under 2 seconds and handles a 100-chunk book without
  loading all chunks into memory.

### Risks

- MCP protocol/SDK version drift — pin the SDK and test against the current
  spec.
- Hosts differ in tool-call timeout and payload limits — keep tools small and
  path-based.
- Security of a local HTTP transport — stdio is the default; HTTP is opt-in.
- Scope creep: the server must not become an LLM client.

## P1 — Headless orchestrator (intermediate)

A `scripts/translate_headless.py` that calls an OpenAI-compatible API directly:

```
python scripts/translate_headless.py --temp-dir <dir> --base-url ... \
  --model ... --api-key-env OPENAI_API_KEY --concurrency 3
```

- Uses the same `get_chunk_prompt` content and `run_state.py` resume logic.
- Parallelizes with a thread pool; retries per chunk.
- Works in CI/cron and on hosts with no sub-agent tool.
- Requires an API key; it is an optional path, not the default.
- Useful as the MCP server's "backend" for scheduled runs.

## P2 — Adapter layer (intermediate / fallback)

Turn `AGENT_ADAPTER.md` into installable adapters:

```
adapters/
  hermes.md
  opencode.md
  claude-code.md
  codex.md
  generic.md
scripts/install_skill.py --host opencode|claude|hermes|...
```

- Copies or symlinks `SKILL.md` + `scripts/` into the host's skill directory.
- Prints the host's sub-agent call syntax and batch formula.
- Keeps the sequential fallback for hosts without sub-agents.
- Covers ZCode, MiniMax Code and Kimi with a "host capability check" template
  until their exact APIs are documented.

This is the cheapest path and should ship before MCP if time is limited.

## P3 — CLI-agent workers (alternative)

Use another CLI agent as the per-chunk worker:

```
python scripts/translate_cli_workers.py --temp-dir <dir> \
  --worker-cmd "opencode run --agent general" --concurrency 3
```

- The orchestrator prepares prompts and pipes them to the worker CLI.
- Useful when the host has shell access but no sub-agent primitive.
- Each adapter is a shell command, not a new pipeline.
- Risks: nested-agent cost, permission prompts, output formatting.

## P4 — Packaging and distribution

- PyPI package with `translate-book` and `translate-book-mcp` entry points.
- Docker image with Python, Calibre and pandoc preinstalled.
- GitHub Action for the smoke test and a release artifact.
- Optional HTTP catalog for OpenCode skills.

## Version plan

| Version | Scope |
|---|---|
| **v1.2.16** | UTF-8 CLI fix, `AGENT_ADAPTER.md`, this roadmap |
| **v1.2.17** | glossary CLI survives a missing glossary.json (found in a real run) |
| **v1.3.0** ✅ | MCP server MVP (stdio, M1–M3), stdlib JSON-RPC, workspace confinement, 56 tests |
| **v1.4.0** | Headless orchestrator, install script, adapter files |
| **v1.5.0** | MCP HTTP transport, auth, Docker image |
| **v2.0.0** | Unified CLI + MCP + all adapters, stable public tool schema |

## Non-goals

- Replacing Calibre or pandoc.
- Bundling or storing LLM API keys.
- Maintaining a separate prompt for every host.
- Rewriting the chunking/merge pipeline for each integration.

## Open questions

1. ~~MCP SDK dependency vs a minimal stdlib JSON-RPC implementation~~ —
   **resolved in v1.3.0: stdlib**. The repo stays dependency-free and
   offline-capable (design principle 1); the implemented surface
   (initialize/ping/tools/resources/prompts over newline-delimited JSON-RPC
   2.0) is small and covered by protocol tests. Revisit only if a client
   refuses the hand-rolled server.
2. One high-level `translate_book` tool vs the granular tools above.
3. How to expose image/binary chunks over MCP without huge payloads.
4. HTTP auth model for shared/remote deployments.
5. Whether ZCode/MiniMax/Kimi expose a stable sub-agent API worth a native
   adapter, or whether MCP covers them first.
