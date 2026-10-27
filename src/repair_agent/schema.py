"""Small versioned contracts shared by the coordinator and model adapter."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
EDITABLE = ("index.html", "style.css")


def clean_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace(chr(0x2014), "-")
    if isinstance(value, list):
        return [clean_text(item) for item in value]
    if isinstance(value, dict):
        return {clean_text(key): clean_text(item) for key, item in value.items()}
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def valid_display_text(self) -> "StrictModel":
        if chr(0x2014) in json.dumps(self.model_dump(), ensure_ascii=False):
            raise ValueError("Forbidden display character")
        return self


class Replacement(StrictModel):
    path: str
    old: str = Field(min_length=1, max_length=4000)
    new: str = Field(max_length=4000)


class Patch(StrictModel):
    base_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    replacements: list[Replacement] = Field(min_length=1, max_length=12)


class Action(StrictModel):
    tool: Literal["inspect_page", "read_source", "propose_patch", "verify_candidate"]
    note: str = Field(max_length=400)
    patch: Patch | None


class RunRequest(StrictModel):
    fixture: str = Field(pattern=r"^[0-9]{2}-[a-z-]+$")
    mode: Literal["scripted", "live"] = "scripted"
    approach: Literal["agent", "single-shot"] = "agent"


class Check(StrictModel):
    id: str
    pass_: bool = Field(alias="pass")
    observation: str


class BrowserResult(StrictModel):
    version: Literal[1]
    axe: dict[str, list[dict[str, Any]]]
    controls: list[dict[str, Any]]
    text: list[dict[str, Any]]
    unsupported: list[str]
    labels: list[Check]
    behavior: list[Check]
    keyboard: list[Check]
    blocked: list[str]
    browser: str
