"""Reproducible local commands; no arbitrary fixture URLs or command execution inputs."""

import argparse
import json
import os
import statistics
import sys
from typing import Any

import uvicorn

from repair_agent.agent import RepairAgent
from repair_agent.fixtures import catalog
from repair_agent.model import Limits, LiveAdapter, ScriptedAdapter
from repair_agent.schema import ROOT, clean_text
from repair_agent.store import Store, now


def summarize(
    rows: list[dict[str, Any]], definitions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    by_id = {row["id"]: row for row in definitions}
    for split in ("development", "held-out"):
        for approach in ("single-shot", "agent"):
            runs = [
                r
                for r in rows
                if r["approach"] == approach and by_id[r["fixture"]]["split"] == split
            ]
            supported = [r for r in runs if by_id[r["fixture"]]["expected"] == "repair"]
            correct = [r for r in runs if by_id[r["fixture"]]["expected"] == "noop"]
            unsupported = [r for r in runs if by_id[r["fixture"]]["expected"] == "unsupported"]
            accepted_regressions = 0
            candidate_regressions = 0
            for run in runs:
                for attempt in run["attempts"]:
                    regression = bool(
                        attempt.get("result")
                        and any(not c["pass"] for c in attempt["result"]["behavior"])
                    )
                    candidate_regressions += int(regression)
                    accepted_regressions += int(regression and attempt["decision"] == "accepted")
            results.append(
                {
                    "split": split,
                    "approach": approach,
                    "pages": len(runs),
                    "verified_repairs": sum(r["status"] == "accepted" for r in supported),
                    "supported_pages": len(supported),
                    "accepted_behavior_regressions": accepted_regressions,
                    "candidate_behavior_regressions": candidate_regressions,
                    "unnecessary_edits": sum(bool(r["attempts"]) for r in correct),
                    "correct_pages": len(correct),
                    "correct_abstentions": sum(
                        r["status"] == "unsupported" and not r["attempts"] for r in unsupported
                    ),
                    "unsupported_pages": len(unsupported),
                    "attempts": sum(len(r["attempts"]) for r in runs),
                    "latency_seconds": round(sum(r.get("latency_seconds", 0) for r in runs), 3),
                    "median_latency_seconds": round(
                        statistics.median([r.get("latency_seconds", 0) for r in runs]), 3
                    )
                    if runs
                    else None,
                    "input_tokens": sum(r["input_tokens"] for r in runs),
                    "output_tokens": sum(r["output_tokens"] for r in runs),
                    "estimated_usd": round(
                        sum(r["estimated_usd"] + r["reserved_usd"] for r in runs), 6
                    ),
                }
            )
    return results


def evaluate(mode: str, budget: float, smoke: bool = False) -> int:
    output = ROOT / "reports" / ("live-smoke.json" if smoke else f"{mode}.json")
    output.parent.mkdir(exist_ok=True)
    if mode == "live" and not os.getenv("OPENAI_API_KEY"):
        output.write_text(
            json.dumps(
                {
                    "version": 1,
                    "mode": mode,
                    "status": "pending",
                    "at": now(),
                    "reason": "OPENAI_API_KEY unavailable; no live API calls made",
                    "runs": [],
                    "summary": [],
                },
                indent=2,
            )
            + "\n"
        )
        print("PENDING: OPENAI_API_KEY unavailable. No live evaluation executed.")
        return 2
    definitions = catalog()
    if smoke:
        definitions = definitions[:1]
    store = Store(ROOT / ".state" / ("smoke" if smoke else f"eval-{mode}"))
    store.recover()
    rows: list[dict[str, Any]] = []
    spent = 0.0
    report: dict[str, Any] = {
        "version": 1,
        "mode": mode,
        "at": now(),
        "status": "running",
        "budget_usd": budget,
        "runs": rows,
        "summary": [],
        "quality_claim": "Scripted pipeline validation only"
        if mode == "scripted"
        else "Measured live model evaluation",
    }
    for definition in definitions:
        for approach in ("single-shot", "agent"):
            if mode == "live" and budget - spent < 0.02:
                report["status"] = "budget_exhausted"
                break
            adapter = LiveAdapter() if mode == "live" else ScriptedAdapter(definition["id"])
            run = store.create(definition["id"], mode, approach, adapter.identifier)
            limits = Limits.environment(min(0.30, budget - spent))
            RepairAgent(store, adapter, limits).run(run)
            spent += run["estimated_usd"] + run["reserved_usd"]
            # Preserve actual tool results, screenshots and exact files in each state manifest.
            rows.append(run)
            report["summary"] = summarize(rows, definitions)
            output.write_text(json.dumps(clean_text(report), indent=2) + "\n")
            print(
                f"{definition['split']:11} {definition['id']:20} {approach:11} "
                f"{run['status']:11} attempts={len(run['attempts'])} {run['reason']}",
                flush=True,
            )
    report["status"] = "completed" if len(rows) == len(definitions) * 2 else "partial"
    report["summary"] = summarize(rows, definitions)
    output.write_text(json.dumps(clean_text(report), indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    if mode == "scripted":
        return int(
            any(r["status"] not in {"accepted", "noop", "unsupported", "rejected"} for r in rows)
        )
    return int(report["status"] != "completed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "eval-fixtures", "eval-live", "smoke-live"])
    parser.add_argument("--budget-usd", type=float, default=3.0)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 0 < args.budget_usd <= 10:
        parser.error("Budget must be greater than zero and at most ten dollars")
    if args.command == "serve":
        uvicorn.run("repair_agent.app:app", host="127.0.0.1", port=args.port)
    else:
        sys.exit(
            evaluate(
                "scripted" if args.command == "eval-fixtures" else "live",
                args.budget_usd,
                args.command == "smoke-live",
            )
        )


if __name__ == "__main__":
    main()
