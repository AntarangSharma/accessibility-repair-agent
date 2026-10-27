"""Scan first-party text, including untracked generated human-facing reports."""

from pathlib import Path

SKIP = {
    ".git",
    ".venv",
    "node_modules",
    ".state",
    "work",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
}
failures = []
for path in Path(".").rglob("*"):
    if not path.is_file() or any(part in SKIP for part in path.parts):
        continue
    try:
        content = path.read_text("utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    if chr(0x2014) in content:
        failures.append(str(path))
if failures:
    raise SystemExit("Forbidden character in: " + ", ".join(failures))
print("Forbidden-character scan passed")
