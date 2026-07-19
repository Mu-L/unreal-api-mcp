# Benchmark harness

Reproducible benchmark behind the README's accuracy numbers.

- `questions-api.json`: 8 pure Unreal API lookups (exact signatures, `#include` paths, deprecations), ground truth from the docs database
- `questions-source.json`: 6 questions answered inside `CharacterMovementComponent.cpp` (about 14,000 lines) from the UE 5.8 engine source, so the answers are grep-able implementation facts, not public API
- `run.py`: runs each question through 3 agent configs (MCP + Grep/Read, Grep/Read, Read only) via headless `claude -p` sessions, collects real token usage, and judges every answer against ground truth with a separate model session
- `results-*.json`: raw outputs of the July 2026 runs
- `gen_charts.py`: renders the README charts (light + dark) from the results

The API-lookup sweep runs in an empty directory on purpose: the engine source is not present, which is the realistic case when you are writing UE C++ in your own game project. The non-MCP configs then have nothing to grep and must answer from model memory. The source sweep points at a checkout of one engine module so every config can grep the same files, which is the fair token comparison.

Re-run:

```bash
python run.py --cwd ./emptydir --questions questions-api.json --out results-api.json
python run.py --cwd /path/to/UnrealEngine/Engine/Source/Runtime/Engine \
              --questions questions-source.json --out results-source.json
python gen_charts.py
```

Point `run.py` at your own UE project directory with your own questions to reproduce the project-research scenario against private code.

Requires an authenticated `claude` CLI and `uvx`. Each full sweep is a few dozen short sessions. Agent behavior changes as models improve, so re-run before quoting numbers.
