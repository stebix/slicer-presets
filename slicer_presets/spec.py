"""JSON preset specification.

A *spec file* holds one or more presets. Two layouts are accepted:

Single preset (legacy layout, still supported)::

    {
      "name": "InnerEar",
      "segments": [ {"name": "Cochlea", "labelValue": 1, "color": "#E6194B"}, ... ],
      "options": { ... }
    }

Multiple presets::

    {
      "version": 1,
      "default": "InnerEar",
      "options": { ... file-wide defaults ... },
      "presets": [ { "name": "InnerEar", "segments": [...], "options": {...} }, ... ]
    }

Segment keys: ``name`` (required), ``color`` (required; ``"#RRGGBB"`` or
``[r, g, b]`` with floats 0-1 or ints 0-255), ``labelValue`` (int > 0),
``id`` (segment ID, defaults to the name), ``order`` (sort key), ``terminology``
(raw Slicer terminology string, optional).

Option keys (camelCase in JSON) are listed in :class:`PresetOptions`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Mapping

SPEC_VERSION = 1

ENV_HOME = "SLICER_PRESETS_HOME"  # repo / package root (added to sys.path by the rc file)
ENV_SPEC = "SLICER_PRESETS_SPEC"  # path of the JSON spec file
ENV_PRESET = "SLICER_PRESET"  # name of the preset to use from that file

DEFAULT_SPEC_RELPATH = Path("presets") / "default.json"

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


class SpecError(ValueError):
    """Raised for a malformed or inconsistent preset specification."""


def parse_color(value: Any, *, where: str = "color") -> tuple[float, float, float]:
    """Return an ``(r, g, b)`` float triple in ``[0, 1]``."""
    if isinstance(value, str):
        m = _HEX_RE.match(value.strip())
        if not m:
            raise SpecError(f"{where}: expected '#RRGGBB', got {value!r}")
        h = m.group(1)
        r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        return (r, g, b)
    if isinstance(value, (list, tuple)) and len(value) == 3 and all(
        isinstance(c, (int, float)) and not isinstance(c, bool) for c in value
    ):
        comps = [float(c) for c in value]
        if any(c < 0 for c in comps):
            raise SpecError(f"{where}: negative colour component in {value!r}")
        if any(c > 1.0 for c in comps):  # 0-255 integers
            comps = [c / 255.0 for c in comps]
        if any(c > 1.0 for c in comps):
            raise SpecError(f"{where}: colour components must be 0-1 or 0-255, got {value!r}")
        return (comps[0], comps[1], comps[2])
    raise SpecError(f"{where}: expected '#RRGGBB' or [r, g, b], got {value!r}")


@dataclass(frozen=True)
class SegmentSpec:
    name: str
    color: tuple[float, float, float]
    label_value: int | None = None
    segment_id: str | None = None
    terminology: str | None = None

    @property
    def requested_id(self) -> str:
        return self.segment_id or self.name


@dataclass(frozen=True)
class PresetOptions:
    """Behaviour switches. JSON keys are the camelCase form of the field names."""

    #: Populate every segmentation node that is *created empty* in the scene
    #: (e.g. Segment Editor "create new segmentation") with the preset segments.
    apply_to_new_segmentations: bool = True
    #: Create a preset segmentation node right after Slicer started.
    create_on_startup: bool = False
    #: Do not create the startup segmentation if the scene already holds one
    #: (e.g. a scene file was passed on the command line).
    skip_if_scene_has_segmentation: bool = True
    #: Switch to the Segment Editor after the startup segmentation was created.
    #: Off by default: creating the editor widget early is what exposed the
    #: Slicer 5.10.0 scene-import crash (see :mod:`slicer_presets.guard`).
    open_segment_editor: bool = False
    #: Install the scene-import guard that works around that crash.
    scene_guard: bool = True
    #: Add "Apply segment preset" to the main window's Edit menu.
    menu_action: bool = True
    #: Name of segmentation nodes created from this preset (default: preset name).
    node_name: str | None = None

    JSON_KEYS: ClassVar[dict[str, str]] = {
        "applyToNewSegmentations": "apply_to_new_segmentations",
        "createOnStartup": "create_on_startup",
        "skipIfSceneHasSegmentation": "skip_if_scene_has_segmentation",
        "openSegmentEditor": "open_segment_editor",
        "sceneGuard": "scene_guard",
        "menuAction": "menu_action",
        "nodeName": "node_name",
    }

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None, base: "PresetOptions | None" = None) -> "PresetOptions":
        values = {f.name: getattr(base, f.name) for f in fields(cls)} if base else {}
        if data is not None and not isinstance(data, Mapping):
            raise SpecError("options: expected an object")
        for key, value in (data or {}).items():
            field = cls.JSON_KEYS.get(key)
            if field is None:
                raise SpecError(f"options: unknown key {key!r} (known: {', '.join(cls.JSON_KEYS)})")
            expected = str if field == "node_name" else bool
            if value is not None and not isinstance(value, expected):
                raise SpecError(f"options.{key}: expected {expected.__name__}, got {value!r}")
            values[field] = value
        return cls(**values)


@dataclass(frozen=True)
class Preset:
    name: str
    segments: tuple[SegmentSpec, ...]
    description: str = ""
    options: PresetOptions = PresetOptions()

    @property
    def node_name(self) -> str:
        return self.options.node_name or self.name


@dataclass(frozen=True)
class PresetFile:
    path: Path | None
    presets: dict[str, Preset]
    default: str

    @property
    def names(self) -> list[str]:
        return list(self.presets)


def _require_str(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{where}: {key!r} must be a non-empty string")
    return value.strip()


def parse_segment(data: Any, index: int, where: str) -> tuple[SegmentSpec, float]:
    """Return the segment and its sort key (``order`` or list position)."""
    here = f"{where}.segments[{index}]"
    if not isinstance(data, Mapping):
        raise SpecError(f"{here}: expected an object")
    name = _require_str(data, "name", here)
    color = parse_color(data.get("color"), where=f"{here}.color")
    label = data.get("labelValue", data.get("label"))
    if label is not None:
        if isinstance(label, bool) or not isinstance(label, int) or label <= 0:
            raise SpecError(f"{here}: labelValue must be a positive integer, got {label!r}")
    segment_id = data.get("id")
    if segment_id is not None and (not isinstance(segment_id, str) or not segment_id.strip()):
        raise SpecError(f"{here}: id must be a non-empty string")
    terminology = data.get("terminology")
    if terminology is not None and not isinstance(terminology, str):
        raise SpecError(f"{here}: terminology must be a string")
    order = data.get("order", index)
    if isinstance(order, bool) or not isinstance(order, (int, float)):
        raise SpecError(f"{here}: order must be a number")
    return SegmentSpec(name, color, label, segment_id, terminology), float(order)


def parse_preset(data: Any, *, file_options: PresetOptions | None = None, where: str = "preset") -> Preset:
    if not isinstance(data, Mapping):
        raise SpecError(f"{where}: expected an object")
    name = _require_str(data, "name", where)
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise SpecError(f"{where} '{name}': 'segments' must be a non-empty list")
    parsed = [parse_segment(s, i, f"{where} '{name}'") for i, s in enumerate(raw_segments)]
    parsed.sort(key=lambda p: p[1])
    segments = tuple(p[0] for p in parsed)

    _check_unique([s.name for s in segments], "segment name", name)
    _check_unique([s.requested_id for s in segments], "segment id", name)
    labels = [s.label_value for s in segments if s.label_value is not None]
    if labels and len(labels) != len(segments):
        raise SpecError(f"preset '{name}': give labelValue for all segments or for none")
    _check_unique(labels, "labelValue", name)

    description = data.get("description", "")
    if not isinstance(description, str):
        raise SpecError(f"preset '{name}': description must be a string")
    options = PresetOptions.from_json(data.get("options"), base=file_options)
    return Preset(name=name, segments=segments, description=description, options=options)


def _check_unique(values: list[Any], what: str, preset: str) -> None:
    seen: set[Any] = set()
    for v in values:
        if v in seen:
            raise SpecError(f"preset '{preset}': duplicate {what} {v!r}")
        seen.add(v)


def parse_spec(data: Any, *, path: Path | None = None) -> PresetFile:
    if not isinstance(data, Mapping):
        raise SpecError("spec: top level must be an object")
    version = data.get("version", SPEC_VERSION)
    if version != SPEC_VERSION:
        raise SpecError(f"spec: unsupported version {version!r} (supported: {SPEC_VERSION})")

    if "presets" in data:
        file_options = PresetOptions.from_json(data.get("options"))
        raw = data["presets"]
        if not isinstance(raw, list) or not raw:
            raise SpecError("spec: 'presets' must be a non-empty list")
        presets = [parse_preset(p, file_options=file_options, where=f"presets[{i}]") for i, p in enumerate(raw)]
    else:
        presets = [parse_preset(data)]

    by_name: dict[str, Preset] = {}
    for p in presets:
        if p.name in by_name:
            raise SpecError(f"spec: duplicate preset name {p.name!r}")
        by_name[p.name] = p

    default = data.get("default", presets[0].name)
    if default not in by_name:
        raise SpecError(f"spec: default preset {default!r} not found (available: {', '.join(by_name)})")
    return PresetFile(path=path, presets=by_name, default=default)


def load_spec_file(path: str | os.PathLike[str]) -> PresetFile:
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise SpecError(f"spec file not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise SpecError(f"{p}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    return parse_spec(data, path=p)


def select_preset(spec: PresetFile, name: str | None = None) -> Preset:
    """Pick a preset: explicit ``name`` > ``$SLICER_PRESET`` > file default."""
    wanted = name or os.environ.get(ENV_PRESET) or spec.default
    try:
        return spec.presets[wanted]
    except KeyError:
        raise SpecError(
            f"preset {wanted!r} not found in {spec.path or 'spec'} (available: {', '.join(spec.names)})"
        ) from None


def package_home() -> Path:
    """Directory that contains the ``slicer_presets`` package (the repo root)."""
    return Path(__file__).resolve().parent.parent


def default_spec_path(home: str | os.PathLike[str] | None = None) -> Path:
    """``$SLICER_PRESETS_SPEC`` if set, else ``<home>/presets/default.json``."""
    env = os.environ.get(ENV_SPEC)
    if env:
        return Path(env)
    base = Path(home) if home else Path(os.environ.get(ENV_HOME) or package_home())
    return base / DEFAULT_SPEC_RELPATH
