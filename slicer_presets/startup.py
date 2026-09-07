"""Wiring executed at Slicer startup (called from ``~/.slicerrc.py``).

``install()`` loads the preset spec and, depending on the preset's options,

* installs the scene-import guard (:mod:`slicer_presets.guard`),
* watches the scene so every segmentation node that is created empty gets the
  preset segments (covers the Segment Editor's own "create new segmentation"),
* adds an *Apply segment preset* action to the Edit menu,
* optionally creates a preset segmentation right away (off by default).

Nothing here switches modules unless ``openSegmentEditor`` is enabled explicitly.
"""

from __future__ import annotations

import logging
from pathlib import Path

import qt
import slicer
import vtk

from . import spec as _spec
from .guard import SegmentEditorImportGuard, segment_editor_module_widget
from .segmentation import (
    PRESET_ATTRIBUTE,
    apply_preset,
    create_segmentation,
    current_source_volume,
    only_default_empty_segments,
    scene_has_segmentation,
    show_in_segment_editor,
)

log = logging.getLogger("slicer_presets")

MENU_ACTION_OBJECT_NAME = "SlicerPresetsApplyAction"


def _status(message: str, timeout_ms: int = 4000) -> None:
    try:
        if not slicer.app.commandOptions().noMainWindow:
            slicer.util.showStatusMessage(message, timeout_ms)
    except Exception:
        pass


class NewSegmentationWatcher:
    """Populate segmentation nodes that are added to the scene empty."""

    def __init__(self, preset: _spec.Preset, scene=None):
        self.preset = preset
        self._scene = scene or slicer.mrmlScene
        self._tag: int | None = None

    def install(self) -> None:
        if self._tag is None:
            self._tag = self._scene.AddObserver(slicer.vtkMRMLScene.NodeAddedEvent, self._on_node_added)

    def uninstall(self) -> None:
        if self._tag is not None:
            self._scene.RemoveObserver(self._tag)
            self._tag = None

    @vtk.calldata_type(vtk.VTK_OBJECT)
    def _on_node_added(self, caller, event, node) -> None:
        if node is None or not node.IsA("vtkMRMLSegmentationNode"):
            return
        if self._scene.IsImporting() or self._scene.IsRestoring():
            return  # nodes coming from a scene file are left untouched
        # Defer: the creator (e.g. the Segment Editor) may still be configuring the node.
        qt.QTimer.singleShot(0, lambda n=node: self.apply_if_empty(n))

    def apply_if_empty(self, node) -> bool:
        if node.GetScene() is None or self._scene.IsImporting():
            return False
        if node.GetAttribute(PRESET_ATTRIBUTE):
            return False
        if not only_default_empty_segments(node):
            return False  # loaded or user-built content; never touch it
        result = apply_preset(node, self.preset)
        n = node.GetSegmentation().GetNumberOfSegments()
        log.info("preset '%s' applied to new segmentation '%s' (%d segments; %s)", self.preset.name, node.GetName(), n, _summary(result))
        _status(f"Segment preset '{self.preset.name}' applied to '{node.GetName()}'")
        return True


def _summary(result: dict[str, list[str]]) -> str:
    return ", ".join(f"{k} {len(v)}" for k, v in result.items() if v) or "no change"


class Installation:
    """Everything ``install()`` set up; ``slicer.modules.slicerPresets`` points at it."""

    def __init__(self, preset: _spec.Preset, spec_file: _spec.PresetFile):
        self.preset = preset
        self.spec_file = spec_file
        self.guard: SegmentEditorImportGuard | None = None
        self.watcher: NewSegmentationWatcher | None = None
        self._menu_action = None

    # -- lifecycle -----------------------------------------------------------------
    def install(self) -> None:
        options = self.preset.options
        if options.scene_guard:
            self.guard = SegmentEditorImportGuard()
            self.guard.install()
        if options.apply_to_new_segmentations:
            self.watcher = NewSegmentationWatcher(self.preset)
            self.watcher.install()
        if options.menu_action:
            self._add_menu_action()
        if options.create_on_startup:
            qt.QTimer.singleShot(0, self.create_startup_segmentation)

    def uninstall(self) -> None:
        if self.guard:
            self.guard.uninstall()
        if self.watcher:
            self.watcher.uninstall()
        if self._menu_action is not None:
            try:
                self._menu_action.parent().removeAction(self._menu_action)
            except Exception:
                pass
            self._menu_action = None

    # -- actions ----------------------------------------------------------------------
    def apply_to_current(self):
        """Apply the preset to the Segment Editor's segmentation (or create one) and show it."""
        widget = segment_editor_module_widget()
        node = widget.editor.segmentationNode() if widget is not None and widget.editor is not None else None
        if node is None:
            node = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLSegmentationNode")
        if node is None:
            node = create_segmentation(self.preset, reference_volume=current_source_volume())
            log.info("created segmentation '%s' from preset '%s'", node.GetName(), self.preset.name)
        else:
            result = apply_preset(node, self.preset)
            log.info("preset '%s' applied to '%s' (%s)", self.preset.name, node.GetName(), _summary(result))
        _status(f"Segment preset '{self.preset.name}' applied to '{node.GetName()}'")
        show_in_segment_editor(node)
        return node

    def create_startup_segmentation(self):
        options = self.preset.options
        if options.skip_if_scene_has_segmentation and scene_has_segmentation():
            log.info("startup segmentation skipped: scene already contains a segmentation")
            return None
        node = create_segmentation(self.preset, reference_volume=current_source_volume())
        log.info("startup segmentation '%s' created from preset '%s'", node.GetName(), self.preset.name)
        if options.open_segment_editor:
            show_in_segment_editor(node)
        return node

    # -- helpers -------------------------------------------------------------------------
    def _add_menu_action(self) -> None:
        try:
            if slicer.app.commandOptions().noMainWindow:
                return
            main_window = slicer.util.mainWindow()
            menu = main_window.findChild(qt.QMenu, "EditMenu") if main_window else None
            if menu is None:
                return
            for old in menu.findChildren(qt.QAction, MENU_ACTION_OBJECT_NAME):
                menu.removeAction(old)
            action = qt.QAction(f"Apply segment preset '{self.preset.name}'", menu)
            action.setObjectName(MENU_ACTION_OBJECT_NAME)
            action.connect("triggered()", self.apply_to_current)
            menu.addAction(action)
            self._menu_action = action
        except Exception:
            log.exception("could not add the Edit-menu action")


def install(spec_path: str | Path | None = None, preset_name: str | None = None, home: str | Path | None = None) -> Installation | None:
    """Load the spec and wire everything up. Never raises: errors are logged and ``None`` is returned."""
    previous = getattr(slicer.modules, "slicerPresets", None)
    if isinstance(previous, Installation):
        previous.uninstall()

    path = Path(spec_path) if spec_path else _spec.default_spec_path(home)
    try:
        spec_file = _spec.load_spec_file(path)
        preset = _spec.select_preset(spec_file, preset_name)
    except _spec.SpecError as exc:
        log.error("slicer-presets: %s", exc)
        _status(f"Segment presets not loaded: {exc}", 10000)
        return None

    installation = Installation(preset, spec_file)
    installation.install()
    slicer.modules.slicerPresets = installation
    o = preset.options
    log.info(
        "slicer-presets: preset '%s' (%d segments) from %s | guard=%s autoApply=%s createOnStartup=%s",
        preset.name, len(preset.segments), path, o.scene_guard, o.apply_to_new_segmentations, o.create_on_startup,
    )
    return installation
