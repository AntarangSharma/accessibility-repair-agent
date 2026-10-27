"""Local review UI. Fixture HTML is never served from this origin."""

import fcntl
import os
import secrets
import threading
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from repair_agent.agent import RepairAgent
from repair_agent.fixtures import catalog, fixture_path
from repair_agent.model import Limits, LiveAdapter, ScriptedAdapter
from repair_agent.schema import ROOT, RunRequest
from repair_agent.store import TERMINAL, Store
from repair_agent.verification import issues


def create_app(state: Path | None = None) -> FastAPI:
    store = Store(state or Path(os.getenv("REPAIR_STATE_DIR", str(ROOT / ".state"))))
    token = secrets.token_urlsafe(32)
    mutex = threading.Lock()
    active: list[str] = []
    executor = ThreadPoolExecutor(max_workers=1)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        with (store.root / "app.lock").open("w") as lockfile:
            try:
                fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Another application owns this state directory") from error
            store.recover()
            yield
            executor.shutdown(wait=True, cancel_futures=True)

    application = FastAPI(
        title="Accessibility Repair Agent", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    application.mount(
        "/static", StaticFiles(directory=ROOT / "src/repair_agent/static"), name="static"
    )
    templates = Jinja2Templates(directory=ROOT / "src/repair_agent/templates")

    @application.middleware("http")
    async def boundaries(request: Request, call_next: Any) -> Any:
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.url.netloc}"
            if origin != expected or not secrets.compare_digest(
                request.headers.get("x-csrf-token", ""), token
            ):
                return JSONResponse({"detail": "Local control request denied"}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def get_run(identifier: str) -> dict[str, Any]:
        try:
            return store.get(identifier)
        except (KeyError, ValueError) as error:
            raise HTTPException(404, "Run not found") from error

    def render(
        request: Request, run: dict[str, Any] | None = None, attempt: int = 0
    ) -> HTMLResponse:
        selected = None
        if run and run["attempts"]:
            selected = run["attempts"][
                max(0, min(attempt or len(run["attempts"]), len(run["attempts"])) - 1)
            ]
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "fixtures": catalog(),
                "runs": store.list()[:20],
                "run": run,
                "selected": selected,
                "csrf": token,
                "live_ready": bool(os.getenv("OPENAI_API_KEY")),
                "terminal": TERMINAL,
                "issues": issues,
            },
        )

    @application.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return render(request)

    @application.get("/runs/{identifier}", response_class=HTMLResponse)
    def detail(request: Request, identifier: str, attempt: int = 0) -> HTMLResponse:
        return render(request, get_run(identifier), attempt)

    @application.get("/api/runs/{identifier}")
    def status(identifier: str) -> dict[str, Any]:
        run = get_run(identifier)
        return {
            "id": run["id"],
            "status": run["status"],
            "reason": run["reason"],
            "calls": run["calls"],
            "attempts": len(run["attempts"]),
            "terminal": run["status"] in TERMINAL,
        }

    @application.post("/api/runs", status_code=202)
    def start(payload: RunRequest) -> dict[str, str]:
        try:
            fixture_path(payload.fixture)
            adapter = LiveAdapter() if payload.mode == "live" else ScriptedAdapter(payload.fixture)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        with mutex:
            if active:
                raise HTTPException(409, "A run is already in progress")
            run = store.create(payload.fixture, payload.mode, payload.approach, adapter.identifier)
            active.append(run["id"])

        def execute() -> None:
            try:
                RepairAgent(store, adapter, Limits.environment()).run(run)
            finally:
                with mutex:
                    active.clear()

        executor.submit(execute)
        return {"id": run["id"], "url": "/runs/" + run["id"]}

    @application.get("/runs/{identifier}/image/{name}")
    def image(identifier: str, name: str) -> FileResponse:
        run = get_run(identifier)
        permitted = {"original.png"} | {f"candidate-{a['number']}.png" for a in run["attempts"]}
        file = store.path(identifier) / name
        if name not in permitted or not file.is_file():
            raise HTTPException(404, "Image not available")
        return FileResponse(file, media_type="image/png")

    @application.get("/runs/{identifier}/manifest")
    def manifest(identifier: str) -> JSONResponse:
        return JSONResponse(
            get_run(identifier), headers={"Content-Disposition": 'attachment; filename="run.json"'}
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
