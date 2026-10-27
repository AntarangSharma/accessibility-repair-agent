"""Only bundled fixtures are addressable. Evaluation labels stay out of model input."""

import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from repair_agent.schema import EDITABLE, ROOT


def catalog() -> list[dict[str, Any]]:
    return json.loads((ROOT / "fixtures/catalog.json").read_text())  # type: ignore[no-any-return]


def fixture_path(identifier: str) -> Path:
    if identifier not in {row["id"] for row in catalog()}:
        raise ValueError("Unknown bundled fixture")
    return ROOT / "fixtures" / identifier


def source(root: Path) -> dict[str, str]:
    return {name: (root / name).read_text() for name in EDITABLE}


def content_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for name, text in source(root).items():
        digest.update(name.encode() + b"\0" + text.encode() + b"\0")
    return digest.hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance(identifier: str) -> dict[str, Any]:
    directory = fixture_path(identifier)
    return {
        "fixture_hashes": {p.name: file_hash(p) for p in sorted(directory.iterdir())},
        "locks": {name: file_hash(ROOT / name) for name in ("uv.lock", "package-lock.json")},
        "oracle_hash": file_hash(ROOT / "browser/runner.mjs"),
        "implementation_hashes": {
            str(p.relative_to(ROOT)): file_hash(p)
            for p in sorted((ROOT / "src/repair_agent").glob("*.py"))
        },
        "python": platform.python_version(),
    }
