"""A fixed argv subprocess and a bounded JSON contract, without shell interpretation."""

import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

from repair_agent.schema import ROOT, BrowserResult, clean_text


class BrowserError(RuntimeError):
    pass


def inspect(fixture: str, root: Path, screenshot: Path, timeout: float = 60) -> dict[str, Any]:
    payload = {
        "version": 1,
        "fixture": fixture,
        "root": str(root.resolve()),
        "screenshot": str(screenshot.resolve()),
    }
    # Never inherit model credentials into the fixture/browser process.
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMPDIR", "PLAYWRIGHT_BROWSERS_PATH", "SYSTEMROOT"}
    }
    process = subprocess.Popen(
        ["node", str(ROOT / "browser/runner.mjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(json.dumps(payload), timeout=max(0.1, timeout))
    except subprocess.TimeoutExpired as error:
        # Kill the whole session, including Chromium, before returning a rejected result.
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise BrowserError("Browser verification timed out") from error
    if process.returncode:
        raise BrowserError("Browser runner failed: " + str(clean_text(stderr[-900:])))
    try:
        data = BrowserResult.model_validate_json(stdout)
        for field in ("violations", "targeted", "incomplete", "targetedIncomplete"):
            if field not in data.axe:
                raise ValueError("Missing axe result group")
        return dict(clean_text(data.model_dump(by_alias=True)))
    except (ValueError, KeyError, TypeError) as error:
        raise BrowserError("Invalid browser v1 response") from error
