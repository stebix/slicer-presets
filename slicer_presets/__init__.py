"""Segment Editor presets for 3D Slicer.

Layout
------
Pure Python (importable and unit-testable *outside* Slicer):

* :mod:`slicer_presets.spec`        JSON preset specification (parse/validate)
* :mod:`slicer_presets.scene_files` sanitiser for ``.mrml`` / ``.mrb`` files
* :mod:`slicer_presets.rcfile`      renders the tiny ``~/.slicerrc.py`` bootstrap
* :mod:`slicer_presets.cli`         ``slicer-presets`` command line (launch, sanitize, ...)

Slicer side (import ``slicer``; only usable inside the Slicer Python runtime):

* :mod:`slicer_presets.segmentation` create / populate segmentation nodes
* :mod:`slicer_presets.guard`        scene-import guard for the Slicer 5.10.0 crash
* :mod:`slicer_presets.startup`      ``install()`` wiring called from ``~/.slicerrc.py``
"""

from .spec import (
    ENV_HOME,
    ENV_PRESET,
    ENV_SPEC,
    Preset,
    PresetFile,
    PresetOptions,
    SegmentSpec,
    SpecError,
    default_spec_path,
    load_spec_file,
    parse_preset,
    select_preset,
)

__version__ = "0.2.0"

__all__ = [
    "ENV_HOME",
    "ENV_PRESET",
    "ENV_SPEC",
    "Preset",
    "PresetFile",
    "PresetOptions",
    "SegmentSpec",
    "SpecError",
    "default_spec_path",
    "install",
    "load_spec_file",
    "parse_preset",
    "select_preset",
]


def install(**kwargs):
    """Entry point used by ``~/.slicerrc.py``; see :func:`slicer_presets.startup.install`."""
    from .startup import install as _install

    return _install(**kwargs)
