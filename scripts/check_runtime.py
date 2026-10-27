"""Fail early before lock installation if Node is outside the tested LTS line."""

import shutil
import subprocess

for command in ("uv", "node", "npm"):
    if not shutil.which(command):
        raise SystemExit(f"{command} is required")
version = subprocess.check_output(["node", "--version"], text=True).strip()
major, minor, *_ = map(int, version.lstrip("v").split("."))
if major != 22 or minor < 12:
    raise SystemExit(f"Use Node 22.12 or newer within Node 22 LTS; found {version}. Run nvm use.")
print(f"Node {version} supported. uv will select Python 3.12 from .python-version.")
