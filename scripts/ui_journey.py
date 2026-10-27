"""One real UI journey, with the production app, background task and Chromium runner."""

import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from repair_agent.schema import ROOT


def main() -> None:
    with tempfile.TemporaryDirectory() as directory, socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
        reservation.close()
        env = os.environ.copy()
        env["REPAIR_STATE_DIR"] = directory
        env.pop("OPENAI_API_KEY", None)
        process = subprocess.Popen(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "repair_agent.cli",
                "serve",
                "--port",
                str(port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(80):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                        break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError("Application exited during startup") from None
                    time.sleep(0.1)
            else:
                raise RuntimeError("Application did not start")
            result = subprocess.run(
                [
                    "node",
                    str(ROOT / "browser/ui-journey.mjs"),
                    f"http://127.0.0.1:{port}",
                    str(ROOT / "reports/ui.png"),
                ],
                check=True,
                text=True,
                capture_output=True,
                timeout=100,
            )
            print(result.stdout.strip())
            manifests = list(Path(directory).glob("*/run.json"))
            assert manifests, "UI did not create a durable run"
            run = json.loads(manifests[0].read_text())
            assert run["status"] == "accepted"
            assert run["attempts"][0]["decision"] == "rejected"
            assert run["attempts"][1]["decision"] == "accepted"
            (ROOT / "reports/ui-journey.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "fixture": run["fixture"],
                        "attempts": [a["decision"] for a in run["attempts"]],
                        "browser_results": [a["result"] for a in run["attempts"]],
                    },
                    indent=2,
                )
                + "\n"
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
