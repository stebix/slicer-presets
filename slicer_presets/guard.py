"""Scene-import guard for the Slicer 5.10.0 Segment Editor crash.

The bug (reproduced on 5.10.0 r34045, absent on 5.8.1): importing a scene whose
saved ``vtkMRMLSegmentEditorNode`` carries ``activeEffectName`` while a
``qMRMLSegmentEditorWidget`` exists ends in an access violation inside
``qSlicerSegmentationsModuleWidgets.dll``. The singleton editor node is
overwritten mid-import, the widget re-activates the stored effect before the
node references are resolved, and dereferences a null pointer.

Workaround, two parts:

1. Detach the Segment Editor widget from its parameter node when the import
   starts, so nothing reacts while the singleton node is being overwritten.
2. When the import has finished, clear ``activeEffectName`` on the imported
   editor node *before* anyone re-attaches to it (the module widget re-attaches
   itself when it is the active module; loading with "clear" resets enough
   widget state that restoring the effect at that point crashes as well).
   Then re-attach if the module did not. Only the remembered active effect is
   lost, which is what the file sanitiser drops too.

The guard never *creates* the Segment Editor widget: instantiating it early is
exactly what made the old startup script trigger the crash on every load.
"""

from __future__ import annotations

import logging

import qt
import slicer

log = logging.getLogger("slicer_presets")

SEGMENT_EDITOR_SINGLETON_TAG = "SegmentEditor"


def segment_editor_module_widget():
    """Python widget of the Segment Editor module if it exists already, else ``None``.

    Never instantiates the module GUI.
    """
    module = getattr(slicer.modules, "segmenteditor", None)
    if module is None:
        return None
    # widgetRepresentation() creates the widget on demand unless creation is
    # disabled (Qt property, no setter method in PythonQt); disable it briefly
    # so the call only returns an already existing widget.
    representation = None
    probed = False
    try:
        enabled = module.widgetRepresentationCreationEnabled
        module.widgetRepresentationCreationEnabled = False
        if module.widgetRepresentationCreationEnabled is False:
            probed = True
            try:
                representation = module.widgetRepresentation()
            finally:
                module.widgetRepresentationCreationEnabled = enabled
    except AttributeError:
        pass
    if not probed:
        # Fallback: look for an existing editor widget in the main window.
        main_window = slicer.util.mainWindow()
        if main_window is None or not slicer.util.findChildren(main_window, className="qMRMLSegmentEditorWidget"):
            return None
        representation = module.widgetRepresentation()
    return representation.self() if representation is not None else None


class SegmentEditorImportGuard:
    def __init__(self, scene=None):
        self._scene = scene or slicer.mrmlScene
        self._tags: list[int] = []
        self._detached = False

    @property
    def installed(self) -> bool:
        return bool(self._tags)

    def install(self) -> None:
        if self._tags:
            return
        # High priority handlers run before the module's own observers, the low
        # priority one after them (so the module gets the first chance to re-attach).
        add = self._scene.AddObserver
        self._tags.append(add(slicer.vtkMRMLScene.StartImportEvent, self._on_start_import, 100.0))
        self._tags.append(add(slicer.vtkMRMLScene.EndImportEvent, self._on_end_import_first, 100.0))
        self._tags.append(add(slicer.vtkMRMLScene.EndImportEvent, self._on_end_import_last, -100.0))

    def uninstall(self) -> None:
        for tag in self._tags:
            self._scene.RemoveObserver(tag)
        self._tags.clear()

    def _on_start_import(self, caller, event) -> None:
        widget = segment_editor_module_widget()
        if widget is None or getattr(widget, "editor", None) is None:
            return
        widget.editor.setMRMLSegmentEditorNode(None)
        widget.parameterSetNode = None
        self._detached = True
        log.debug("scene import started: Segment Editor detached from its parameter node")

    def _editor_node(self):
        return self._scene.GetSingletonNode(SEGMENT_EDITOR_SINGLETON_TAG, "vtkMRMLSegmentEditorNode")

    def _on_end_import_first(self, caller, event) -> None:
        if not self._detached:
            return  # no editor widget existed: an effect restored later on enter() is fine
        node = self._editor_node()
        if node is None:
            return
        if node.GetActiveEffectName():
            log.debug("scene import finished: dropping saved active effect %r", node.GetActiveEffectName())
            node.SetActiveEffectName("")
        # Remember what the scene wants shown; the widget's own end-of-batch sync
        # can wipe these after a detach/re-attach.
        self._restore = (node.GetSegmentationNode(), node.GetSourceVolumeNode())

    RESTORE_RETRY_MS = 100
    RESTORE_MAX_TRIES = 30  # ~3 s

    def _restore_selection(self, tries: int = 0) -> None:
        segmentation, volume = getattr(self, "_restore", (None, None))
        widget = segment_editor_module_widget()
        if widget is None or getattr(widget, "editor", None) is None:
            self._restore = (None, None)
            return
        editor = widget.editor
        if segmentation is None or segmentation.GetScene() is None or editor.segmentationNodeID():
            self._restore = (None, None)
            return
        # The node combobox is refilled asynchronously after the import; a selection
        # made before that is silently dropped, so retry until it sticks.
        editor.setSegmentationNode(segmentation)
        if editor.segmentationNodeID():
            if volume is not None and volume.GetScene() is not None and not editor.sourceVolumeNodeID():
                editor.setSourceVolumeNode(volume)
            log.debug("restored Segment Editor segmentation %s after import (try %d)", segmentation.GetID(), tries + 1)
            self._restore = (None, None)
        elif tries + 1 < self.RESTORE_MAX_TRIES:
            qt.QTimer.singleShot(self.RESTORE_RETRY_MS, lambda: self._restore_selection(tries + 1))
        else:
            log.debug("could not restore Segment Editor segmentation after import")
            self._restore = (None, None)

    def _on_end_import_last(self, caller, event) -> None:
        if not self._detached:
            return
        self._detached = False
        widget = segment_editor_module_widget()
        if widget is None or getattr(widget, "editor", None) is None:
            return
        # Selection is restored after the import's batch processing has ended.
        qt.QTimer.singleShot(0, self._restore_selection)
        if widget.parameterSetNode is not None:
            return  # the module re-attached itself (it was the active module)
        node = self._editor_node()
        if node is None:
            return  # the module creates one the next time it is entered
        widget.parameterSetNode = node
        widget.editor.setMRMLSegmentEditorNode(node)
        log.debug("scene import finished: Segment Editor re-attached to %s", node.GetID())
