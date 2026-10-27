"""Independent acceptance rules. The model has no vote in this decision."""

from typing import Any


def violations(scan: dict[str, Any], field: str = "violations") -> set[str]:
    return {
        item["id"] + ":" + str(node["target"])
        for item in scan["axe"][field]
        for node in item["nodes"]
    }


def issues(scan: dict[str, Any]) -> int:
    return len(violations(scan, "targeted")) + sum(not c["pass"] for c in scan["keyboard"])


def decide(baseline: dict[str, Any], candidate: dict[str, Any]) -> tuple[bool, str]:
    if candidate["unsupported"]:
        return False, "Candidate introduced or retained unsupported content"
    if issues(candidate) >= issues(baseline):
        return False, "Targeted issues did not improve"
    if issues(candidate):
        return False, "Candidate leaves targeted failures unresolved"
    if violations(candidate) - violations(baseline):
        return False, "New scoped axe violation"
    if violations(candidate, "incomplete") - violations(baseline, "incomplete"):
        return False, "New incomplete scoped axe result requires manual review"
    for category in ("behavior", "labels", "keyboard"):
        if not all(check["pass"] for check in candidate[category]):
            return False, f"Independent {category} assertion failed"
    if candidate["blocked"]:
        return False, "Unexpected browser request was blocked"
    before = baseline["controls"]
    after = candidate["controls"]
    if len(before) != len(after):
        return False, "Relevant control added or removed"
    for old, new in zip(before, after, strict=True):
        if old["id"] != new["id"] or old["name"] != new["name"] or old["text"] != new["text"]:
            return False, "Relevant control identity changed"
        if not new["visible"] or new["disabled"]:
            return False, "Relevant control hidden or disabled"
        if old["tag"] == "input" and (new["tag"] != "input" or old["type"] != new["type"]):
            return False, "Input semantics changed"
        for dimension in ("width", "height"):
            if abs(old["box"][dimension] - new["box"][dimension]) > max(
                12, old["box"][dimension] * 0.2
            ):
                return False, "Control layout changed beyond the v1 tolerance"
    if [(t["text"], t["visible"]) for t in baseline["text"]] != [
        (t["text"], t["visible"]) for t in candidate["text"]
    ]:
        return False, "Text removed, hidden, or changed"
    return True, "Targeted issues resolved; independent behavior and scoped scans passed"
