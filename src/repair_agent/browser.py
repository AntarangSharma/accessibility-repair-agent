"""A fixed argv subprocess and a bounded JSON contract, without shell interpretation."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from repair_agent.schema import ROOT, clean_text


class BrowserError(RuntimeError):
    pass


def inspect(fixture: str, root: Path, screenshot: Path, timeout: float = 60) -> dict[str, Any]:
    payload = {'version': 1, 'fixture': fixture, 'root': str(root.resolve()),
               'screenshot': str(screenshot.resolve())}
    # Never inherit model credentials into the fixture/browser process.
    env = {key: value for key, value in os.environ.items()
           if key in {'PATH', 'HOME', 'TMPDIR', 'PLAYWRIGHT_BROWSERS_PATH', 'SYSTEMROOT'}}
    try:
        result = subprocess.run(
            ['node', str(ROOT / 'browser/runner.mjs')], input=json.dumps(payload),
            text=True, capture_output=True, timeout=max(0.1, timeout), check=False, env=env,
        )
    except subprocess.TimeoutExpired as error:
        raise BrowserError('Browser verification timed out') from error
    if result.returncode:
        raise BrowserError('Browser runner failed: ' + str(clean_text(result.stderr[-900:])))
    try:
        data = json.loads(result.stdout)
        if data['version'] != 1 or not all(key in data for key in
                ('axe', 'behavior', 'keyboard', 'controls', 'labels', 'unsupported')):
            raise ValueError('Invalid runner result')
        return dict(clean_text(data))
    except (ValueError, KeyError, TypeError) as error:
        raise BrowserError('Invalid browser v1 response') from error
