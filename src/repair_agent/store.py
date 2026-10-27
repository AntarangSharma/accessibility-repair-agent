"""SQLite is authoritative; run.json is a durable, portable review manifest."""

import json
import os
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from repair_agent.fixtures import fixture_path, provenance
from repair_agent.schema import clean_text

TERMINAL = {"accepted", "rejected", "noop", "unsupported", "failed", "interrupted"}


def now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, directory: Path):
        self.root = directory.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "state.sqlite3"
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=15)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def save(self, run: dict[str, Any]) -> None:
        run["updated_at"] = now()
        payload = json.dumps(clean_text(run), indent=2, ensure_ascii=False) + "\n"
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?)", (run["id"], payload))
        directory = self.path(run["id"])
        directory.mkdir(exist_ok=True)
        temporary = directory / "run.json.tmp"
        with temporary.open("w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(directory / "run.json")
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def path(self, identifier: str) -> Path:
        if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
            raise ValueError("Invalid run ID")
        return self.root / identifier

    def get(self, identifier: str) -> dict[str, Any]:
        self.path(identifier)
        with self.connection() as db:
            row = db.execute("SELECT payload FROM runs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        return dict(json.loads(row[0]))

    def list(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            return [
                json.loads(row[0])
                for row in db.execute("SELECT payload FROM runs ORDER BY rowid DESC")
            ]

    def create(self, fixture: str, mode: str, approach: str, model: str) -> dict[str, Any]:
        original = fixture_path(fixture)
        run: dict[str, Any] = {
            "version": 1,
            "id": uuid4().hex,
            "fixture": fixture,
            "mode": mode,
            "approach": approach,
            "model": model,
            "status": "created",
            "created_at": now(),
            "attempts": [],
            "trace": [],
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_usd": 0.0,
            "reserved_usd": 0.0,
            "accepted_path": None,
            "baseline": None,
            "reason": "",
            **provenance(fixture),
        }
        self.save(run)  # Journal intent before copying anything.
        shutil.copytree(original, self.path(run["id"]) / "original")
        return run

    def recover(self) -> int:
        recovered = 0
        for run in self.list():
            if run["status"] in TERMINAL:
                continue
            for attempt in run["attempts"]:
                if attempt["decision"] == "pending":
                    attempt["decision"] = "interrupted"
                    attempt["reason"] = "Verification interrupted; candidate never accepted"
            working = self.path(run["id"]) / "working"
            if working.exists():
                shutil.rmtree(working)
            run.update(
                status="interrupted",
                accepted_path=None,
                reason="Restart recovery rolled back unverified work",
            )
            self.save(run)
            recovered += 1
        return recovered
