"""Fail-closed edits limited to a small, non-executable HTML/CSS vocabulary."""

import difflib
import os
import re
from pathlib import Path

import tinycss2
from bs4 import BeautifulSoup, Tag

from repair_agent.fixtures import content_hash, source
from repair_agent.schema import EDITABLE, Patch


class PatchError(ValueError):
    pass


def validate_html(original: str, candidate: str) -> None:
    before, after = BeautifulSoup(original, "html.parser"), BeautifulSoup(candidate, "html.parser")
    allowed_tags = {element.name for element in before.find_all()} | {"label", "button"}
    if any(element.name not in allowed_tags for element in after.find_all()):
        raise PatchError("New HTML tag outside repair scope")
    if [str(el) for el in before.find_all("script")] != [
        str(el) for el in after.find_all("script")
    ]:
        raise PatchError("Scripts are immutable")
    for tag in ("head",):
        if str(before.find(tag)) != str(after.find(tag)):
            raise PatchError("Document head is immutable")
    if before.get_text(" ", strip=True) != after.get_text(" ", strip=True):
        raise PatchError("Visible content cannot be removed or rewritten")
    allowed_attributes = {"for", "aria-label", "aria-labelledby", "type", "role", "tabindex"}
    for element in after.find_all():
        for key, value in element.attrs.items():
            if key.lower().startswith("on") or key in {
                "style",
                "srcdoc",
                "hidden",
                "inert",
                "aria-hidden",
                "disabled",
            }:
                raise PatchError("Executable or inline style attributes prohibited")
            if key in {"href", "src", "action", "formaction"} and re.search(
                r"(?i)javascript:|data:|https?:|//", str(value)
            ):
                raise PatchError("External or executable URL prohibited")
    # Existing IDs, names, classes, data attributes, form ownership, and event selectors survive.
    old_ids = [el.get("id") for el in before.select("[id]")]
    new_ids = [el.get("id") for el in after.select("[id]")]
    if old_ids != new_ids:
        raise PatchError("Control IDs cannot change")
    for old in before.select("[id]"):
        new = after.find(id=old["id"])
        if not isinstance(new, Tag):
            raise PatchError("Control removed")
        if old.name in {"input", "button"} and (
            old.name != new.name
            or old.get("tabindex") != new.get("tabindex")
            or old.get("role") != new.get("role")
        ):
            raise PatchError("Existing native control keyboard semantics are immutable")
        for key in set(old.attrs) | set(new.attrs):
            if key not in allowed_attributes and old.get(key) != new.get(key):
                raise PatchError("Selector or form attribute changed")
        if old.find_parent("form") is not None and new.find_parent("form") is None:
            raise PatchError("Control moved outside form")
    if [el.attrs for el in before.select("form")] != [el.attrs for el in after.select("form")]:
        raise PatchError("Form attributes are immutable")
    if len(before.select("input, form, [data-action]")) != len(
        after.select("input, form, [data-action]")
    ):
        raise PatchError("Relevant control count changed")


def validate_css(original: str, candidate: str) -> None:
    def rules(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
        result = []
        for rule in tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True):
            if rule.type != "qualified-rule":
                raise PatchError("CSS imports, at-rules, and parse errors prohibited")
            declarations = tinycss2.parse_declaration_list(
                rule.content, skip_comments=True, skip_whitespace=True
            )
            if any(item.type != "declaration" or item.important for item in declarations):
                raise PatchError("CSS must use ordinary declarations")
            result.append(
                (
                    tinycss2.serialize(rule.prelude).strip(),
                    [(d.name, tinycss2.serialize(d.value).strip()) for d in declarations],
                )
            )
        return result

    before, after = rules(original), rules(candidate)
    if len(before) != len(after):
        raise PatchError("CSS rule count cannot change")
    for (selector, old), (new_selector, new) in zip(before, after, strict=True):
        if selector != new_selector or [p for p, _ in old] != [p for p, _ in new]:
            raise PatchError("CSS selectors and properties cannot change")
        for (prop, old_value), (_, value) in zip(old, new, strict=True):
            if old_value != value and (
                prop not in {"color", "background", "background-color"}
                or not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value)
            ):
                raise PatchError("Only solid hex color repairs are supported")


def apply_patch(root: Path, patch: Patch) -> str:
    if root.is_symlink():
        raise PatchError("Symlink root prohibited")
    for name in EDITABLE:
        path = root / name
        if path.is_symlink() or path.resolve().parent != root.resolve():
            raise PatchError("Symlink escape prohibited")
    if content_hash(root) != patch.base_hash:
        raise PatchError("Stale base hash")
    if sum(len(r.old.encode()) + len(r.new.encode()) for r in patch.replacements) > 12000:
        raise PatchError("Patch exceeds 12000 bytes")
    original = source(root)
    updated = original.copy()
    for replacement in patch.replacements:
        if replacement.path not in EDITABLE:
            raise PatchError("Only index.html and style.css may change")
        text = updated[replacement.path]
        if text.count(replacement.old) != 1:
            raise PatchError("Replacement must match exactly once")
        updated[replacement.path] = text.replace(replacement.old, replacement.new, 1)
    validate_html(original["index.html"], updated["index.html"])
    validate_css(original["style.css"], updated["style.css"])
    if updated == original:
        raise PatchError("Empty change")
    diff = "".join(
        "".join(
            difflib.unified_diff(
                original[name].splitlines(keepends=True),
                updated[name].splitlines(keepends=True),
                fromfile="original/" + name,
                tofile="candidate/" + name,
            )
        )
        for name in EDITABLE
    )
    # All validation completes before the first file is changed.
    for name, text in updated.items():
        with (root / name).open("w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return diff
