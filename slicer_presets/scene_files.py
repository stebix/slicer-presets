"""Sanitise Slicer scene files (``.mrml`` and ``.mrb`` bundles).

Slicer 5.10.0 crashes (access violation in ``qSlicerSegmentationsModuleWidgets.dll``)
when a scene is imported while the Segment Editor widget exists and the scene's
saved ``SegmentEditor`` node carries an ``activeEffectName``: the widget re-activates
that effect in the middle of the import. Stripping the attribute from the file
makes the scene load cleanly; nothing else is lost but the remembered active effect.

Modes:

* ``active-effect`` (default) - remove only ``activeEffectName`` (proven sufficient).
* ``selection``  - also remove ``selectedSegmentID`` and ``maskSegmentID``.
* ``node``       - remove the whole ``SegmentEditor`` node (all editor UI state).
"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

SEGMENT_EDITOR_NODE_RE = re.compile(r"<SegmentEditor\b.*?</SegmentEditor>", re.S)

MODES: dict[str, tuple[str, ...]] = {
    "active-effect": ("activeEffectName",),
    "selection": ("activeEffectName", "selectedSegmentID", "maskSegmentID"),
    "node": (),
}
DEFAULT_MODE = "active-effect"


def sanitize_mrml_text(text: str, mode: str = DEFAULT_MODE) -> tuple[str, int]:
    """Return ``(new_text, number_of_changes)``."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r} (choose from {', '.join(MODES)})")
    changes = 0

    def _fix_node(match: re.Match[str]) -> str:
        nonlocal changes
        node = match.group(0)
        if mode == "node":
            changes += 1
            return ""
        for attr in MODES[mode]:
            node, n = re.subn(r'\s+' + attr + r'="[^"]*"', "", node)
            changes += n
        return node

    return SEGMENT_EDITOR_NODE_RE.sub(_fix_node, text), changes


def _default_output(path: Path) -> Path:
    return path.with_name(f"{path.stem}.safe{path.suffix}")


def sanitize_mrml_file(
    path: str | os.PathLike[str], output: str | os.PathLike[str] | None = None, mode: str = DEFAULT_MODE
) -> tuple[Path, int]:
    src = Path(path)
    dst = Path(output) if output else _default_output(src)
    text = src.read_text(encoding="utf-8")
    new_text, changes = sanitize_mrml_text(text, mode)
    dst.write_text(new_text, encoding="utf-8")
    return dst, changes


def sanitize_mrb(
    path: str | os.PathLike[str], output: str | os.PathLike[str] | None = None, mode: str = DEFAULT_MODE
) -> tuple[Path, int]:
    """Copy an ``.mrb`` bundle, rewriting the embedded ``.mrml`` scene(s)."""
    src = Path(path)
    dst = Path(output) if output else _default_output(src)
    if dst.resolve() == src.resolve():
        raise ValueError("output must differ from input")
    changes = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info)
            if info.filename.lower().endswith(".mrml"):
                text, n = sanitize_mrml_text(data.decode("utf-8"), mode)
                changes += n
                data = text.encode("utf-8")
            zout.writestr(info, data, compress_type=info.compress_type)
    return dst, changes


def sanitize_scene_file(
    path: str | os.PathLike[str], output: str | os.PathLike[str] | None = None, mode: str = DEFAULT_MODE
) -> tuple[Path, int]:
    suffix = Path(path).suffix.lower()
    if suffix == ".mrb":
        return sanitize_mrb(path, output, mode)
    if suffix == ".mrml":
        return sanitize_mrml_file(path, output, mode)
    raise ValueError(f"not a Slicer scene file (.mrml/.mrb): {path}")


def needs_sanitizing(path: str | os.PathLike[str], mode: str = DEFAULT_MODE) -> bool:
    """True if sanitising would change the file."""
    p = Path(path)
    if p.suffix.lower() == ".mrb":
        with zipfile.ZipFile(p) as z:
            texts = [z.read(i).decode("utf-8") for i in z.infolist() if i.filename.lower().endswith(".mrml")]
    elif p.suffix.lower() == ".mrml":
        texts = [p.read_text(encoding="utf-8")]
    else:
        return False
    return any(sanitize_mrml_text(t, mode)[1] > 0 for t in texts)
