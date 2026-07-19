#!/usr/bin/env python3
"""Reproducible benchmark: Unreal API MCP vs plain research agents.

Runs each question in the questions file through three agent configs using
headless `claude -p` sessions, collects real token usage from the CLI's JSON
output, then judges each answer against the ground truth with a separate judge
session.

For the API-lookup sweep the sessions run in a neutral empty directory: the
Unreal Engine source is not present, which is the realistic case when you are
writing UE C++ in your own game project. The non-MCP configs then have nothing
to grep and must answer from model memory, exactly the situation the MCP server
is meant to fix.

Usage:
  python run.py --cwd /path/to/workdir [--model sonnet]
                [--questions questions-api.json] [--out results-api.json]
                [--only q1,q2] [--configs mcp,skilled,naive]

Requires: claude CLI on PATH and authenticated; uvx (for the MCP config).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

MCP_CONFIG = {
    "mcpServers": {
        "unreal-api": {
            "command": "uvx",
            "args": ["unreal-api-mcp"],
            "env": {"UNREAL_VERSION": "5.8"},
        }
    }
}

CONFIGS = {
    # Realistic MCP workflow: project reads allowed, Unreal API facts via MCP
    "mcp": {
        "label": "MCP + targeted Read",
        "tools": "mcp__unreal-api__*,Grep,Glob,Read",
        "mcp": True,
        "note": (
            "Use the unreal-api MCP tools for any Unreal Engine C++ API fact "
            "(signatures, #include paths, deprecations) instead of inferring "
            "from memory. Use Grep/Read only for project-specific logic."
        ),
    },
    # Skilled agent without MCP: targeted grep + partial reads
    "skilled": {
        "label": "Skilled (Grep+Read)",
        "tools": "Grep,Glob,Read",
        "mcp": False,
        "note": (
            "Work efficiently: if the engine source is available, locate code "
            "with Grep and read only the relevant line ranges."
        ),
    },
    # Naive agent: file reads only
    "naive": {
        "label": "Naive (full Reads)",
        "tools": "Glob,Read",
        "mcp": False,
        "note": "Find answers by listing and reading files.",
    },
}

PROMPT_TEMPLATE = """You are researching Unreal Engine 5.8 C++ to answer one question precisely.

Question: {question}

{note}

Answer requirements:
- Name the exact classes/functions/#include paths involved
- If an Unreal Engine API is part of the answer, state its exact name, signature, or header
- 2-5 sentences, factual, no speculation. If unsure, say what you could not verify.
"""

JUDGE_TEMPLATE = """You are grading a research agent's answer about the Unreal Engine 5.8 C++ API.

Question: {question}

Ground truth (verified): {ground_truth}
Key Unreal APIs involved: {unreal_apis}

Agent's answer:
---
{answer}
---

Respond with ONLY a JSON object, no other text:
{{"verdict": "correct" | "partial" | "wrong",
  "hallucinated_api": true | false,  // did it name an Unreal API, class, header, or signature that does not exist?
  "hallucination_detail": "<name it if any, else empty>",
  "reason": "<one sentence>"}}
"""


def run_claude(prompt: str, cwd: Path, model: str, tools: str, use_mcp: bool,
               max_turns: int = 20) -> dict:
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--max-turns", str(max_turns),
        "--allowedTools", tools,
        "--disallowedTools", "Bash,Write,Edit,WebFetch,WebSearch,Agent,Task",
    ]
    if use_mcp:
        mcp_path = HERE / "mcp-config.json"
        mcp_path.write_text(json.dumps(MCP_CONFIG))
        cmd += ["--mcp-config", str(mcp_path), "--strict-mcp-config"]
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError(f"claude failed: {out.stderr[-500:]}")
    return json.loads(out.stdout)


def billed_tokens(usage: dict) -> int:
    """Cost-weighted tokens: full price for fresh input/output, 10% for cache reads."""
    return int(
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + 0.1 * usage.get("cache_read_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )


def context_tokens(usage: dict) -> int:
    """Fresh context moved through the model: input + cache creation + output."""
    return int(
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True,
                    help="Working directory for the sessions (empty dir for API lookups, "
                         "engine module checkout for source research).")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--questions", default=str(HERE / "questions-api.json"))
    ap.add_argument("--out", default=str(HERE / "results-api.json"))
    ap.add_argument("--only", default="")
    ap.add_argument("--configs", default="mcp,skilled,naive")
    args = ap.parse_args()

    cwd = Path(args.cwd).resolve()
    questions = json.loads(Path(args.questions).read_text())
    if args.only:
        keep = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in keep]
    config_keys = [c for c in args.configs.split(",") if c in CONFIGS]

    out_path = Path(args.out)
    results = json.loads(out_path.read_text()) if out_path.exists() else {}

    for q in questions:
        results.setdefault(q["id"], {})
        for key in config_keys:
            if results[q["id"]].get(key):
                print(f"[skip] {q['id']}/{key} (already done)")
                continue
            cfg = CONFIGS[key]
            print(f"[run ] {q['id']}/{key} ...", flush=True)
            prompt = PROMPT_TEMPLATE.format(question=q["question"], note=cfg["note"])
            try:
                res = run_claude(prompt, cwd, args.model, cfg["tools"], cfg["mcp"])
            except Exception as e:
                print(f"[fail] {q['id']}/{key}: {e}", file=sys.stderr)
                continue
            answer = res.get("result", "")
            judge_prompt = JUDGE_TEMPLATE.format(
                question=q["question"], ground_truth=q["ground_truth"],
                unreal_apis=", ".join(q.get("unreal_apis", [])), answer=answer,
            )
            judge_raw = subprocess.run(
                ["claude", "-p", judge_prompt, "--output-format", "json",
                 "--model", args.model, "--max-turns", "1",
                 "--disallowedTools", "*"],
                capture_output=True, text=True, timeout=300,
            )
            try:
                jr = json.loads(judge_raw.stdout)
                verdict = json.loads(
                    jr.get("result", "{}").strip().removeprefix("```json").removesuffix("```").strip("` \n")
                )
            except Exception:
                verdict = {"verdict": "unjudged", "hallucinated_api": False,
                           "hallucination_detail": "", "reason": "judge output unparseable"}
            usage = res.get("usage", {})
            results[q["id"]][key] = {
                "answer": answer,
                "verdict": verdict,
                "usage": usage,
                "billed_tokens": billed_tokens(usage),
                "context_tokens": context_tokens(usage),
                "num_turns": res.get("num_turns"),
                "duration_ms": res.get("duration_ms"),
                "cost_usd": res.get("total_cost_usd"),
            }
            out_path.write_text(json.dumps(results, indent=2))
            print(f"[done] {q['id']}/{key}: {results[q['id']][key]['context_tokens']} ctx tokens, "
                  f"{verdict.get('verdict')}")

    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
