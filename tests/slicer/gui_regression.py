"""GUI regression for the Slicer 5.10.0 scene-import crash. Run with the rc hook active:

    Slicer.exe --no-splash --python-script tests/slicer/gui_regression.py

Scenario (this crashed before): Segment Editor opened at startup, then a scene
whose SegmentEditor node has an active effect is imported. With the import guard
installed by ~/.slicerrc.py the load must succeed and the preset must be applied
to a segmentation created afterwards. Exit code 0 on success.

Set SLICER_PRESETS_TEST_MRB to the scene file to use: any .mrb or .mrml saved
while a Segment Editor effect was selected (that is what sets activeEffectName
on the SegmentEditor node). Without it this test reports SKIP and exits 0.
"""

import os
import sys
import traceback
from pathlib import Path

import qt
import slicer

MRB = os.environ.get("SLICER_PRESETS_TEST_MRB", "")
failures = []


def check(cond, msg):
    print(("[gui] PASS " if cond else "[gui] FAIL ") + msg)
    if not cond:
        failures.append(msg)


def finish():
    print(f"[gui] {'OK' if not failures else 'FAILED: ' + '; '.join(failures)}")
    slicer.app.exit(0 if not failures else 1)


def step1_open_editor():
    try:
        inst = getattr(slicer.modules, "slicerPresets", None)
        check(inst is not None, "rc hook installed slicer.modules.slicerPresets")
        slicer.util.selectModule("SegmentEditor")  # the editor creates an empty segmentation on enter
        qt.QTimer.singleShot(1500, step2_check_preset_then_load)
    except Exception:
        traceback.print_exc()
        failures.append("step1 exception")
        finish()


def step2_check_preset_then_load():
    try:
        nodes = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        check(len(nodes) == 1, f"editor created one segmentation ({len(nodes)})")
        n = nodes[0].GetSegmentation().GetNumberOfSegments() if nodes else 0
        check(n == 5, f"preset applied to the editor's segmentation ({n} segments)")
        print("[gui] loading scene:", MRB)
        slicer.util.loadScene(MRB, {"clear": True})  # like File > Load Scene: replaces the scene
        print("[gui] scene loaded without crash")
        qt.QTimer.singleShot(1500, step3_after_load)
    except Exception:
        traceback.print_exc()
        failures.append("step2 exception")
        finish()


def step3_after_load():
    try:
        w = slicer.modules.segmenteditor.widgetRepresentation().self()
        check(w.parameterSetNode is not None, "Segment Editor re-attached to its parameter node")
        node = slicer.mrmlScene.GetSingletonNode("SegmentEditor", "vtkMRMLSegmentEditorNode")
        check(node is not None and w.editor.mrmlSegmentEditorNode() is node, "widget uses the scene's singleton editor node")
        segs = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        print("[gui] segmentation nodes after import:", [s.GetName() for s in segs])
        imported = [s for s in segs if s.GetName() == "Segmentation"]
        check(len(imported) == 1 and imported[0].GetSegmentation().GetNumberOfSegments() == 2, "imported segmentation intact (2 segments)")
        check(imported and imported[0].GetAttribute("SlicerPresets.Preset") is None, "imported segmentation not touched by the watcher")
        shown = w.editor.segmentationNodeID()
        ref = node.GetSegmentationNode() if node else None
        print("[gui] editor segmentation node ID after import:", repr(shown), "| node ref:", ref.GetID() if ref else None,
              "| source volume:", repr(w.editor.sourceVolumeNodeID()), "| active effect:", repr(w.editor.activeEffect().name if w.editor.activeEffect() else None))
        check(bool(imported) and shown == imported[0].GetID(), "editor shows the imported segmentation")
        # a new segmentation created after the import still gets the preset
        fresh = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "AfterImport")
        qt.QTimer.singleShot(200, lambda: step4_final(fresh))
    except Exception:
        traceback.print_exc()
        failures.append("step3 exception")
        finish()


def step4_final(fresh):
    try:
        check(fresh.GetSegmentation().GetNumberOfSegments() == 5, "preset applied to segmentation created after import")
        # and loading the same scene a second time (editor still open) is fine as well
        slicer.util.loadScene(MRB, {"clear": True})
        print("[gui] second scene load OK")
    except Exception:
        traceback.print_exc()
        failures.append("step4 exception")
    qt.QTimer.singleShot(1000, finish)


def step0_check_inputs():
    if not MRB:
        print("[gui] SKIP: set SLICER_PRESETS_TEST_MRB to a scene saved with a Segment Editor effect active")
        return slicer.app.exit(0)
    if not Path(MRB).is_file():
        failures.append("scene file not found: " + MRB)
        return finish()
    step1_open_editor()


qt.QTimer.singleShot(1000, step0_check_inputs)
qt.QTimer.singleShot(90000, lambda: (failures.append("timeout"), finish()))
