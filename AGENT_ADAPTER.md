# Running the pipeline on any agent

The translation engine is host-agnostic: everything under `scripts/` is plain
Python, and `SKILL.md` is a natural-language workflow. Only the orchestration
glue changes between agents.

A run consists of:

1. `convert.py` — book → Markdown chunks
2. a glossary + `run_state.py plan` — decide what needs translating
3. one isolated worker per chunk — translate + write `output_chunk*.md`
4. `merge_meta.py` — merge worker observations into the glossary
5. `merge_and_build.py` — merge → HTML → DOCX/EPUB/PDF

Steps 1, 2, 4 and 5 are pure CLI and identical everywhere. Step 3 is where the
host adapter matters.

## Capability contract

An orchestrator needs:

1. **Shell** — run `python scripts/...`.
2. **Files** — read/write UTF-8 files.
3. **Workers** — spawn an isolated sub-agent with a prompt (ideally several in
   parallel).
4. **Wait** — detect completion and inspect the output files.

If (3) is missing, use **sequential mode**: translate one chunk at a time, each
in a fresh context. The result is identical; only wall-clock time changes.

## Portable vs host-specific

| Concern | Portable? | Adapter action |
|---|---|---|
| `scripts/*.py` | yes | run with the host's shell tool |
| glossary / manifest / run_state / meta schemas | yes | none |
| translation prompts in `SKILL.md` | yes | none |
| build pipeline (pandoc + Calibre) | yes | install dependencies |
| `SKILL.md` frontmatter | partly | keep `name` and `description`; other hosts may ignore or reject extra keys |
| skill install location | no | put `SKILL.md` + `scripts/` where the host discovers skills |
| sub-agent primitive | no | map to the host's Task/delegate/subagent tool |
| concurrency cap | no | size batches after `tasks-per-call × parallel-calls` |
| interpreter name | no | `python` on Hermes/Windows, `python3` on Linux/macOS or inside a venv |
| file/glob tool names | no | the workflow says "read/write/glob"; map to host tools |

## Host adapters

| Host | Install | Sub-agent primitive |
|---|---|---|
| **Hermes** | its skills directory | `delegate_task` with a `tasks` array, max 3 tasks per call |
| **OpenCode** | `.opencode/skills/translate-book-parallel-pro/SKILL.md` (project) or `~/.config/opencode/skills/...` (global); OpenCode also reads `.claude/skills` and `.agents/skills` | its subagent/Task tool; in this environment `subagent` with `agent: "general"` |
| **Claude Code** | `.claude/skills/translate-book-parallel-pro/SKILL.md` | `Task` / `Agent` tool with a general-purpose sub-agent |
| **Codex** | host skill/instruction directory | its task/spawn primitive, otherwise sequential |
| **ZCode / MiniMax Code / Kimi** | host skill/instruction directory | check for a Task/delegate/subagent tool; if none, sequential |
| **Generic chat agent** | paste `SKILL.md` as instructions | sequential, or any "new conversation per chunk" feature |

OpenCode derives the skill ID from the directory name; the frontmatter `name`
is only a display label. Extra frontmatter fields such as `allowed-tools` and
`metadata.hermes` are ignored by OpenCode.

If a host only supports plain project instructions (`AGENTS.md`, a system
prompt, etc.), put the contents of `SKILL.md` there and keep `scripts/` next to
it. The scripts use `{baseDir}`-relative paths, so the layout matters more than
the packaging.

## Sub-agent prompt contract

Each worker must receive:

- absolute path to `chunkNNNN.md`
- absolute path to `output_chunkNNNN.md`
- target language
- the translation rules from `SKILL.md` §4
- the term table from `glossary.py print-terms-for-chunk`
- neighbor excerpts from `chunk_context.py`
- instruction to write `output_chunkNNNN.meta.json`

The worker should write files directly. If it can only return text, the
orchestrator writes the output itself; that works for short chunks but risks
truncation on long ones.

## Batch sizing

`concurrency` in `SKILL.md` is the number of chunks per batch. The host may cap
how many tasks one worker call can carry:

```
batch_size = min(concurrency, tasks_per_call × parallel_calls)
```

Examples:

- Hermes: 3 tasks per `delegate_task` call; 8 calls → 24-chunk batch.
- OpenCode: spawn independent subagent calls in parallel; cap by the host's
  parallelism and rate limits.
- No subagents: batch size 1 (sequential).

## Dependencies and interpreter

```bash
python scripts/setup.py          # checks Python, Calibre, pandoc, pypandoc, bs4
pip install -r requirements.txt  # pinned tested versions
```

- `python` is used in the docs for Hermes venv compatibility. On Linux/macOS
  use `python3` or activate a venv so `python` exists.
- `ebook-convert` (Calibre) and `pandoc` must be on `PATH`. On Windows Calibre
  is usually `C:\Program Files\Calibre2\ebook-convert.exe` — add its directory
  to `PATH`.
- UTF-8 CLI output is configured by `scripts/_stdio.py`, so glossary tables
  and translated JSON no longer crash on Windows cp1251/cp866 consoles.

## Fully host-independent options

If you want to remove the dependency on host sub-agents entirely:

1. **Headless orchestrator** — a Python CLI that calls an OpenAI-compatible
   API directly for each chunk. Requires an API key and model configuration;
   the host agent only runs the CLI.
2. **MCP server (v1.3.0, shipped)** — `python scripts/mcp_server.py
   --workspace <root>` exposes the pipeline as MCP tools over stdio
   (`convert_book`, `get_status`, `get_translation_plan`, `get_chunk_prompt`,
   `submit_translation`, `merge_meta`, `validate_book`, `build_book`). Any
   MCP-capable agent drives the whole run without a custom adapter: it calls
   `convert_book`, fetches `get_chunk_prompt` per chunk, translates the prompt
   itself or spawns workers, writes results with `submit_translation`, and
   finishes with `validate_book` + `build_book`. The server never calls an
   LLM and confines every path to the workspace root.
3. **CLI-agent workers** — use `opencode run`, `claude -p`, or another CLI
   agent as the per-chunk worker. The main orchestrator stays the same; only
   the "spawn worker" command changes.

The current design intentionally uses the host LLM, so it needs no API key and
no second model. Options 1–3 are useful when the host has no sub-agent tool or
when you want the same orchestration in CI/cron.

### Connecting agents to the MCP server

The same server command is registered once per host; every MCP-capable agent
then drives the pipeline with zero repo edits. Start it from the repository
root so `--workspace .` matches the project.

**OpenCode** — add a `mcp` section to the project `opencode.json` (or the
global `~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "translate-book": {
      "type": "local",
      "command": ["python", "scripts/mcp_server.py", "--workspace", "."],
      "enabled": true
    }
  }
}
```

**ZCode** — add the server to the workspace config `<repo>/.zcode/config.json`
(user scope: `~/.zcode/cli/config.json`); workspace-scoped servers are trusted
and auto-connected at session start:

```json
{
  "mcp": {
    "servers": {
      "translate-book": {
        "command": "python",
        "args": ["scripts/mcp_server.py", "--workspace", "."]
      }
    }
  }
}
```

Both hosts need `python` on PATH and the repo's tool deps (`ebook-convert`,
`pandoc`) installed for `convert_book`/`build_book`; the other tools work
without them. Other MCP clients (Claude Code, Codex, Cursor) use the same
command with their own stdio server config format.

## Smoke-testing a new host

```bash
python scripts/setup.py
python scripts/convert.py tests/baselines/sleepy-hollow/sleepy-hollow.epub \
  --olang ru --chunk-size 6000 --temp-root tests/.artifacts/host-test
python scripts/run_state.py plan tests/.artifacts/host-test/sleepy-hollow_temp
```

Then translate **one** chunk with the host's worker, verify that
`output_chunk0001.md` is non-empty, and only after that launch the full batch.
This catches missing tool permissions and encoding issues before spending
tokens on the whole book.
