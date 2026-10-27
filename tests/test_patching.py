import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from repair_agent.fixtures import content_hash, fixture_path
from repair_agent.patching import PatchError, apply_patch
from repair_agent.schema import Action, Patch, Replacement
from repair_agent.store import Store


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    result = tmp_path / "copy"
    shutil.copytree(fixture_path("01-newsletter"), result)
    return result


def patch(
    copy: Path,
    old: str = "<p>Email address</p>",
    new: str = '<label for="email">Email address</label>',
    path: str = "index.html",
) -> Patch:
    return Patch(
        base_hash=content_hash(copy), replacements=[Replacement(path=path, old=old, new=new)]
    )


@pytest.mark.parametrize(
    "path",
    [
        "../index.html",
        "/tmp/index.html",
        "trusted.js",
        "contract.json",
        "tests/test.py",
        "sub/index.html",
    ],
)
def test_path_scope(copy: Path, path: str) -> None:
    before = content_hash(copy)
    with pytest.raises(PatchError):
        apply_patch(copy, patch(copy, path=path))
    assert content_hash(copy) == before


def test_stale_hash(copy: Path) -> None:
    item = patch(copy)
    (copy / "style.css").write_text((copy / "style.css").read_text() + "\n")
    with pytest.raises(PatchError, match="Stale"):
        apply_patch(copy, item)


@pytest.mark.parametrize("old", ["not present", ">"])
def test_exactly_one_match(copy: Path, old: str) -> None:
    before = content_hash(copy)
    with pytest.raises(PatchError, match="exactly once"):
        apply_patch(copy, patch(copy, old=old))
    assert content_hash(copy) == before


@pytest.mark.parametrize(
    "new",
    [
        "<script>alert(1)</script><p>Email address</p>",
        '<p onclick="alert(1)">Email address</p>',
        '<p style="display:none">Email address</p>',
        '<iframe src="https://example.com"></iframe><p>Email address</p>',
    ],
)
def test_executable_edits_rejected(copy: Path, new: str) -> None:
    with pytest.raises(PatchError):
        apply_patch(copy, patch(copy, new=new))


def test_script_source_is_immutable(copy: Path) -> None:
    with pytest.raises(PatchError):
        apply_patch(copy, patch(copy, old='src="trusted.js"', new='src="other.js"'))


def test_css_scope(copy: Path) -> None:
    with pytest.raises(PatchError):
        apply_patch(
            copy, patch(copy, old="color: #172b36", new="color: transparent", path="style.css")
        )


def test_symlink_escape(copy: Path, tmp_path: Path) -> None:
    item = patch(copy)
    target = tmp_path / "outside.html"
    target.write_text((copy / "index.html").read_text())
    (copy / "index.html").unlink()
    (copy / "index.html").symlink_to(target)
    with pytest.raises(PatchError, match="Symlink"):
        apply_patch(copy, item)


def test_forbidden_model_display_character() -> None:
    with pytest.raises(ValidationError):
        Action(tool="read_source", note="a" + chr(0x2014) + "b", patch=None)


def test_recovery_never_accepts_unverified_candidate(tmp_path: Path) -> None:
    store = Store(tmp_path / "state")
    run = store.create("01-newsletter", "scripted", "agent", "scripted-v1")
    root = store.path(run["id"])
    shutil.copytree(root / "original", root / "working")
    apply_patch(root / "working", patch(root / "working"))
    run.update(status="verifying", attempts=[{"decision": "pending", "reason": ""}])
    store.save(run)
    assert Store(store.root).recover() == 1
    recovered = store.get(run["id"])
    assert recovered["status"] == "interrupted"
    assert recovered["accepted_path"] is None
    assert recovered["attempts"][0]["decision"] == "interrupted"
    assert not (root / "working").exists()
    assert content_hash(root / "original") == content_hash(fixture_path("01-newsletter"))
    assert store.recover() == 0
