import json
import shutil
from pathlib import Path

import pytest

from repair_agent.browser import inspect
from repair_agent.fixtures import content_hash, fixture_path
from repair_agent.patching import apply_patch
from repair_agent.schema import Patch, Replacement
from repair_agent.verification import decide, issues


@pytest.mark.browser
def test_seeded_problems_and_label_slice(tmp_path: Path) -> None:
    for fixture, expected in [("01-newsletter", 1), ("04-notice", 1), ("06-listener", 2)]:
        original = fixture_path(fixture)
        baseline = inspect(fixture, original, tmp_path / f"{fixture}.png")
        assert issues(baseline) == expected
        assert all(check["pass"] for check in baseline["behavior"])
        if fixture != "01-newsletter":
            continue
        candidate = tmp_path / "candidate"
        shutil.copytree(original, candidate)
        patch = Patch(
            base_hash=content_hash(candidate),
            replacements=[
                Replacement(
                    path="index.html",
                    old="<p>Email address</p>",
                    new='<label for="email">Email address</label>',
                )
            ],
        )
        diff = apply_patch(candidate, patch)
        assert "+<html" not in diff
        result = inspect(fixture, candidate, tmp_path / "repaired.png")
        assert decide(baseline, result)[0]
        (tmp_path / "label-evidence.json").write_text(
            json.dumps({"baseline": baseline, "candidate": result})
        )
