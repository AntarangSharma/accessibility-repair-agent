import copy
import shutil
from pathlib import Path
from typing import Any

import pytest

from repair_agent.agent import RepairAgent
from repair_agent.browser import BrowserError, inspect
from repair_agent.fixtures import content_hash, fixture_path
from repair_agent.model import Limits, ScriptedAdapter
from repair_agent.patching import apply_patch
from repair_agent.schema import Action, Patch, Replacement
from repair_agent.store import Store
from repair_agent.verification import decide, issues


def baseline() -> dict[str, Any]:
    return {
        "version": 1,
        "axe": {
            "violations": [],
            "incomplete": [],
            "targeted": [{"id": "label", "nodes": [{"target": ["#email"]}]}],
        },
        "keyboard": [],
        "behavior": [{"id": "submit", "pass": True}],
        "labels": [],
        "controls": [],
        "text": [],
        "unsupported": [],
        "blocked": [],
    }


class RepeatingAdapter:
    identifier = "test adapter"

    def __init__(self, action: str):
        self.action = action

    def choose(
        self, observation: dict[str, Any], limits: Limits, timeout: float
    ) -> tuple[Action, dict[str, int]]:
        item = None
        tool = self.action
        if tool == "propose_patch":
            if not observation["source"]:
                tool = "read_source"
            else:
                item = Patch(
                    base_hash=observation["base_hash"],
                    replacements=[
                        Replacement(
                            path="index.html", old="missing original text", new="irrelevant"
                        )
                    ],
                )
        return Action(tool=tool, note="Test limit handling", patch=item), {
            "input_tokens": 0,
            "output_tokens": 0,
        }


def test_three_attempt_limit_and_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repair_agent.agent.inspect", lambda *a, **k: baseline())
    store = Store(tmp_path)
    run = store.create("01-newsletter", "scripted", "agent", "test")
    result = RepairAgent(store, RepeatingAdapter("propose_patch")).run(run)
    assert result["status"] == "rejected"
    assert len(result["attempts"]) == 3
    assert all(a["decision"] == "rejected" for a in result["attempts"])
    assert result["accepted_path"] is None
    assert content_hash(store.path(run["id"]) / "original") == content_hash(
        fixture_path("01-newsletter")
    )


def test_call_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repair_agent.agent.inspect", lambda *a, **k: baseline())
    store = Store(tmp_path)
    run = store.create("01-newsletter", "scripted", "agent", "test")
    result = RepairAgent(store, RepeatingAdapter("inspect_page"), Limits(calls=2)).run(run)
    assert result["calls"] == 2
    assert result["status"] == "rejected"
    assert not result["attempts"]


def test_spend_reserved_before_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repair_agent.agent.inspect", lambda *a, **k: baseline())
    store = Store(tmp_path)
    run = store.create("01-newsletter", "live", "agent", "test")
    result = RepairAgent(store, RepeatingAdapter("inspect_page"), Limits(spend_usd=0.000001)).run(
        run
    )
    assert result["calls"] == 0
    assert "spend" in result["reason"]


def test_elapsed_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repair_agent.agent.inspect", lambda *a, **k: baseline())
    store = Store(tmp_path)
    run = store.create("01-newsletter", "scripted", "agent", "test")
    result = RepairAgent(store, RepeatingAdapter("inspect_page"), Limits(seconds=0)).run(run)
    assert result["status"] == "rejected"
    assert result["calls"] == 0


def test_verification_timeout_never_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fake_inspect(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return baseline()
        raise BrowserError("Browser verification timed out")

    monkeypatch.setattr("repair_agent.agent.inspect", fake_inspect)
    store = Store(tmp_path)
    run = store.create("01-newsletter", "scripted", "agent", "test")
    result = RepairAgent(store, ScriptedAdapter("01-newsletter")).run(run)
    assert len(result["attempts"]) == 3
    assert all(
        a["decision"] == "rejected" and "timed out" in a["reason"] for a in result["attempts"]
    )
    assert result["accepted_path"] is None


@pytest.mark.parametrize("change", ["new_violation", "hidden", "wrong_label"])
def test_independent_rejection_rules(change: str) -> None:
    original = baseline()
    original["controls"] = [
        {
            "id": "email",
            "name": "email",
            "text": "",
            "visible": True,
            "disabled": False,
            "tag": "input",
            "type": "email",
            "box": {"width": 200, "height": 40},
        }
    ]
    candidate = copy.deepcopy(original)
    candidate["axe"]["targeted"] = []
    if change == "new_violation":
        candidate["axe"]["violations"] = [{"id": "button-name", "nodes": [{"target": ["button"]}]}]
    elif change == "hidden":
        candidate["controls"][0]["visible"] = False
    else:
        candidate["labels"] = [{"pass": False}]
    assert not decide(original, candidate)[0]


@pytest.mark.browser
def test_axe_improvement_cannot_override_form_regression(tmp_path: Path) -> None:
    fid = "01-newsletter"
    original = fixture_path(fid)
    before = inspect(fid, original, tmp_path / "before.png")
    candidate = tmp_path / "candidate"
    shutil.copytree(original, candidate)
    apply_patch(
        candidate,
        Patch(
            base_hash=content_hash(candidate),
            replacements=[
                Replacement(
                    path="index.html",
                    old="<p>Email address</p>",
                    new='<label for="email">Email address</label>',
                ),
                Replacement(
                    path="index.html",
                    old='id="submit" type="submit"',
                    new='id="submit" type="button"',
                ),
            ],
        ),
    )
    after = inspect(fid, candidate, tmp_path / "after.png")
    assert issues(before) > issues(after) == 0
    assert not after["behavior"][0]["pass"]
    assert not decide(before, after)[0]


@pytest.mark.browser
def test_real_runner_timeout(tmp_path: Path) -> None:
    with pytest.raises(BrowserError, match="timed out"):
        inspect(
            "01-newsletter", fixture_path("01-newsletter"), tmp_path / "timeout.png", timeout=0.1
        )


@pytest.mark.browser
@pytest.mark.parametrize(
    "fid,expected",
    [("13-correct-form", "noop"), ("16-ambiguous", "unsupported"), ("17-gradient", "unsupported")],
)
def test_noop_and_abstention(tmp_path: Path, fid: str, expected: str) -> None:
    store = Store(tmp_path)
    run = store.create(fid, "scripted", "agent", "scripted-v1")
    result = RepairAgent(store, ScriptedAdapter(fid)).run(run)
    assert result["status"] == expected
    assert result["calls"] == 0
    assert result["attempts"] == []
    assert result["accepted_path"] is None


def test_call_limit_discards_pending_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repair_agent.agent.inspect", lambda *a, **k: baseline())
    store = Store(tmp_path)
    run = store.create("01-newsletter", "scripted", "agent", "scripted-v1")
    result = RepairAgent(store, ScriptedAdapter("01-newsletter"), Limits(calls=3)).run(run)
    assert result["status"] == "rejected"
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["decision"] == "rejected"
    assert result["pending"] is None and result["accepted_path"] is None


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), -1, 0])
def test_invalid_price_cannot_bypass_spend_limit(rate: float) -> None:
    with pytest.raises(ValueError):
        Limits(input_rate=rate)
