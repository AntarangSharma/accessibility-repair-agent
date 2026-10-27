"""A single bounded LangGraph agent with deterministic verification and rollback."""

import json
import shutil
import time
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from repair_agent.browser import BrowserError, inspect
from repair_agent.fixtures import content_hash, source
from repair_agent.model import SYSTEM, Adapter, Limits
from repair_agent.patching import PatchError, apply_patch
from repair_agent.schema import Action, clean_text
from repair_agent.store import Store, now
from repair_agent.verification import decide, issues


class GraphState(TypedDict):
    done: bool
    action: dict[str, Any] | None


class RepairAgent:
    def __init__(self, store: Store, adapter: Adapter, limits: Limits | None = None):
        self.store = store
        self.adapter = adapter
        self.limits = limits or Limits()
        self.run_data: dict[str, Any] = {}
        self.started = 0.0
        self.observed = False
        self.read = False

    def save(self) -> None:
        self.run_data["latency_seconds"] = round(time.monotonic() - self.started, 3)
        self.store.save(self.run_data)

    def finish(self, status: str, reason: str) -> None:
        if status != "accepted":
            for attempt in self.run_data["attempts"]:
                if attempt["decision"] == "pending":
                    attempt.update(
                        decision="rejected", reason="Unverified candidate discarded: " + reason
                    )
            self.run_data["pending"] = None
            self.run_data["accepted_path"] = None
        self.run_data.update(status=status, reason=reason, completed_at=now())
        self.save()

    def remaining(self) -> float:
        return self.limits.seconds - (time.monotonic() - self.started)

    @property
    def directory(self) -> Path:
        return self.store.path(self.run_data["id"])

    def observation(self) -> dict[str, Any]:
        run = self.run_data
        # Do not include catalog outcomes, test source, scripted patches, or contract.json.
        scan = run["baseline"]
        summary = {
            key: scan[key]
            for key in ("axe", "controls", "text", "keyboard", "behavior", "labels", "unsupported")
        }
        return {
            "inspected": self.observed,
            "source": source(self.directory / "original") if self.read else {},
            "base_hash": content_hash(self.directory / "original"),
            "pending": bool(run.get("pending")),
            "attempts": len(run["attempts"]),
            "remaining_attempts": self.limits.attempts - len(run["attempts"]),
            "inspection": summary if self.observed else {"target_count": issues(scan)},
            "feedback": [
                {
                    "decision": a["decision"],
                    "reason": a["reason"],
                    "result": a.get("result"),
                    "diff": a.get("diff", ""),
                }
                for a in run["attempts"][-1:]
            ],
            "allowed_tools": ["inspect_page", "read_source", "propose_patch", "verify_candidate"],
        }

    def choose(self, state: GraphState) -> GraphState:
        run = self.run_data
        if self.remaining() <= 1 or run["calls"] >= self.limits.calls:
            self.finish("rejected", "Elapsed-time or model-call limit reached")
            return {"done": True, "action": None}
        if len(run["attempts"]) >= self.limits.attempts and not run.get("pending"):
            self.finish("rejected", "Three-candidate attempt limit reached")
            return {"done": True, "action": None}
        observation = self.observation()
        size = len(json.dumps(observation).encode()) + len(SYSTEM.encode())
        if size > self.limits.input_bytes:
            self.finish("rejected", "Model input size limit reached")
            return {"done": True, "action": None}
        reserve = self.limits.reservation(size) if run["mode"] == "live" else 0.0
        if run["estimated_usd"] + run["reserved_usd"] + reserve > self.limits.spend_usd:
            self.finish("rejected", "Estimated-spend limit reached before next API call")
            return {"done": True, "action": None}
        run["calls"] += 1
        run["reserved_usd"] += reserve
        self.save()  # Reserve before the network request, including failed requests.
        if run["approach"] == "single-shot":
            observation["allowed_tools"] = ["propose_patch"]
            observation["instruction"] = (
                "Single-shot baseline: return your only propose_patch action now"
            )
        action, usage = self.adapter.choose(observation, self.limits, self.remaining())
        run["provider_model"] = getattr(self.adapter, "resolved_model", self.adapter.identifier)
        run["reserved_usd"] -= reserve
        for field in ("input_tokens", "output_tokens"):
            run[field] += usage[field]
        run["estimated_usd"] += (
            usage["input_tokens"] * self.limits.input_rate
            + usage["output_tokens"] * self.limits.output_rate
        ) / 1_000_000
        if run["approach"] == "single-shot" and action.tool != "propose_patch":
            self.finish("rejected", "Single-shot model did not return a patch proposal")
            return {"done": True, "action": None}
        run["trace"].append({"tool": action.tool, "decision": action.note, "at": now()})
        self.save()
        return {"done": False, "action": action.model_dump()}

    def execute(self, state: GraphState) -> GraphState:
        action = Action.model_validate(state["action"])
        run = self.run_data
        if action.tool == "inspect_page":
            self.observed = True  # The preflight is an actual, cached browser observation.
            run["trace"][-1]["observation"] = "Original browser inspection returned"
        elif action.tool == "read_source":
            self.read = True
            run["trace"][-1]["observation"] = "Pristine HTML/CSS and SHA-256 returned"
        elif action.tool == "propose_patch":
            if action.patch is None:
                self.finish("unsupported", "Model abstained: " + action.note)
                return {"done": True, "action": None}
            if run.get("pending") or not self.read:
                run["trace"][-1]["observation"] = (
                    "Read source first; verify pending patch before proposing"
                )
            else:
                self.propose(action)
                if run["approach"] == "single-shot" and run.get("pending"):
                    self.verify()
                if run["status"] == "accepted":
                    return {"done": True, "action": None}
                if run["approach"] == "single-shot":
                    self.finish("rejected", run["attempts"][-1]["reason"])
                    return {"done": True, "action": None}
        elif run.get("pending"):
            self.verify()
            if run["status"] == "accepted":
                return {"done": True, "action": None}
        else:
            run["trace"][-1]["observation"] = "No pending candidate to verify"
        self.save()
        return {"done": False, "action": None}

    def propose(self, action: Action) -> None:
        run = self.run_data
        number = len(run["attempts"]) + 1
        attempt: dict[str, Any] = {
            "number": number,
            "decision": "pending",
            "reason": "",
            "patch": action.patch.model_dump() if action.patch else None,
            "diff": "",
            "result": None,
        }
        run["attempts"].append(attempt)
        run["status"] = "proposing"
        self.save()  # Journal planned copy and patch before filesystem side effects.
        candidate = self.directory / f"candidate-{number}"
        shutil.copytree(self.directory / "original", candidate)
        try:
            if action.patch is None:
                raise PatchError("Missing patch")
            attempt["diff"] = apply_patch(candidate, action.patch)
            run["pending"] = number
            run["status"] = "candidate"
        except (PatchError, OSError, ValueError) as error:
            attempt.update(decision="rejected", reason=str(clean_text(str(error))))
            run["status"] = "running"
        self.save()

    def verify(self) -> None:
        run = self.run_data
        number = run["pending"]
        attempt = run["attempts"][number - 1]
        run["status"] = "verifying"
        self.save()  # A crash after this point must never imply acceptance.
        try:
            result = inspect(
                run["fixture"],
                self.directory / f"candidate-{number}",
                self.directory / f"candidate-{number}.png",
                timeout=min(60, self.remaining()),
            )
            attempt["result"] = result
            accepted, reason = decide(run["baseline"], result)
        except BrowserError as error:
            accepted, reason = False, str(error)
        attempt.update(decision="accepted" if accepted else "rejected", reason=reason)
        run["pending"] = None
        if accepted:
            run["accepted_path"] = f"candidate-{number}"
            run["accepted_hash"] = content_hash(self.directory / f"candidate-{number}")
            self.finish("accepted", reason)
        else:
            # No candidate becomes the active artifact. Retain rejected evidence for review.
            run.update(status="running", accepted_path=None)
            self.save()

    def run(self, run: dict[str, Any]) -> dict[str, Any]:
        self.run_data = run
        self.started = time.monotonic()
        run["limits"] = vars(self.limits)
        run["status"] = "inspecting"
        self.save()
        try:
            run["baseline"] = inspect(
                run["fixture"],
                self.directory / "original",
                self.directory / "original.png",
                timeout=min(60, self.remaining()),
            )
            self.save()
            if run["baseline"]["unsupported"]:
                self.finish("unsupported", "; ".join(run["baseline"]["unsupported"]))
                return run
            if issues(run["baseline"]) == 0:
                if all(
                    c["pass"]
                    for category in ("behavior", "labels")
                    for c in run["baseline"][category]
                ):
                    self.finish("noop", "No supported failure; original files unchanged")
                else:
                    self.finish(
                        "unsupported", "Independent contract failed without a supported axe issue"
                    )
                return run
            run["status"] = "running"
            if run["approach"] == "single-shot":
                self.observed = self.read = True
            graph = StateGraph(GraphState)
            graph.add_node("choose", self.choose)
            graph.add_node("execute", self.execute)
            graph.add_edge(START, "choose")
            graph.add_conditional_edges("choose", lambda s: END if s["done"] else "execute")
            graph.add_conditional_edges("execute", lambda s: END if s["done"] else "choose")
            graph.compile().invoke({"done": False, "action": None}, {"recursion_limit": 32})
        except Exception as error:
            # API exceptions can carry private request metadata. Persist only the class.
            for attempt in run["attempts"]:
                if attempt["decision"] == "pending":
                    attempt.update(
                        decision="rejected", reason="Run failed before verification completed"
                    )
            run["pending"] = None
            run["accepted_path"] = None
            reason = (
                str(error)
                if isinstance(error, (BrowserError, PatchError))
                else type(error).__name__
            )
            self.finish("failed", "Run failed: " + str(clean_text(reason)))
        return run
