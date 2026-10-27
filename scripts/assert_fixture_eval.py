"""Scripted expectations validate the pipeline, never live AI quality."""

import json
from pathlib import Path

report = json.loads(Path("reports/scripted.json").read_text())
assert report["status"] == "completed"
assert len(report["runs"]) == 36
for row in report["summary"]:
    assert row["accepted_behavior_regressions"] == 0
    assert row["unnecessary_edits"] == 0
    assert row["correct_abstentions"] == row["unsupported_pages"]
    if row["approach"] == "agent":
        assert row["verified_repairs"] == row["supported_pages"]
print("All scripted evaluation contracts passed")
