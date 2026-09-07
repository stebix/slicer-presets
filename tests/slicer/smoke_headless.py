"""Headless smoke test of the Slicer-side code. Run with:

    Slicer.exe --no-main-window --ignore-slicerrc --python-script tests/slicer/smoke_headless.py

Exit code 0 on success. The repo root is derived from this file's location.
"""

import os
import sys
import traceback
from pathlib import Path

HOME = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HOME))
os.environ["SLICER_PRESETS_HOME"] = str(HOME)

import slicer  # noqa: E402

failures = []


def check(cond, msg):
    print(("[smoke] PASS " if cond else "[smoke] FAIL ") + msg)
    if not cond:
        failures.append(msg)


try:
    import slicer_presets
    from slicer_presets.segmentation import PRESET_ATTRIBUTE, apply_preset, only_default_empty_segments

    inst = slicer_presets.install()
    check(inst is not None, "install() returned an Installation")
    check(inst.preset.name == "InnerEar" and len(inst.preset.segments) == 5, "default preset loaded")
    check(inst.guard is not None and inst.guard.installed, "scene guard installed")
    check(inst.watcher is not None, "new-segmentation watcher installed")
    from slicer_presets.guard import segment_editor_module_widget

    check(segment_editor_module_widget() is None, "widget probe finds no Segment Editor widget (none created yet)")
    enabled = slicer.modules.segmenteditor.widgetRepresentationCreationEnabled
    check(enabled() if callable(enabled) else enabled, "widget creation re-enabled after the probe")

    # 1) a segmentation created empty gets populated (deferred via QTimer -> pump events)
    node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "Fresh")
    slicer.app.processEvents()
    seg = node.GetSegmentation()
    check(seg.GetNumberOfSegments() == 5, f"empty node populated ({seg.GetNumberOfSegments()} segments)")
    names = [seg.GetNthSegment(i).GetName() for i in range(seg.GetNumberOfSegments())]
    check(names == [s.name for s in inst.preset.segments], f"segment order {names}")
    labels = [seg.GetNthSegment(i).GetLabelValue() for i in range(seg.GetNumberOfSegments())]
    check(labels == [1, 2, 3, 4, 5], f"label values {labels}")
    c = seg.GetNthSegment(0).GetColor()
    check(abs(c[0] - 0xE6 / 255) < 1e-6 and abs(c[1] - 0x19 / 255) < 1e-6, f"first colour {c}")
    check(node.GetAttribute(PRESET_ATTRIBUTE) == "InnerEar", "preset attribute set")

    # 2) Segment Editor style: node + default 'Segment_1' placeholder -> adopted, no stray segment
    node2 = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "EditorStyle")
    sid = node2.GetSegmentation().AddEmptySegment("", "Segment_1")
    slicer.app.processEvents()
    seg2 = node2.GetSegmentation()
    check(seg2.GetNumberOfSegments() == 5, f"placeholder adopted, total {seg2.GetNumberOfSegments()}")
    check(seg2.GetSegment(sid).GetName() == "Cochlea", "Segment_1 became the first preset segment")

    # 3) content that already exists is never touched by the watcher
    node3 = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "UserMade")
    node3.GetSegmentation().AddEmptySegment("", "Tumour")
    slicer.app.processEvents()
    check(node3.GetSegmentation().GetNumberOfSegments() == 1, "user-named segment left alone")
    check(not only_default_empty_segments(node3), "only_default_empty_segments() false for user content")

    # 4) explicit apply merges: updates existing, adds missing, keeps user segments
    result = apply_preset(node3, inst.preset)
    check(node3.GetSegmentation().GetNumberOfSegments() == 6, "explicit apply added 5 segments next to user segment")
    check(len(result["added"]) == 5 and not result["adopted"], f"apply result {result}")
    result = apply_preset(node3, inst.preset)
    check(len(result["updated"]) == 5 and not result["added"], "second apply only updates")

    # 5) importing a scene does not trigger the watcher and the guard survives it
    mrb = Path(os.environ.get("SLICER_PRESETS_TEST_MRB", ""))
    if mrb.is_file():
        before = {n.GetID() for n in slicer.util.getNodesByClass("vtkMRMLSegmentationNode")}
        slicer.util.loadScene(str(mrb), {"clear": True})
        slicer.app.processEvents()
        after = slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        imported = [n for n in after if n.GetID() not in before or n.GetName() == "Segmentation"]
        print(f"[smoke] segmentation nodes after import: {[n.GetName() for n in after]}")
        check(len(imported) >= 1, "scene import added the bundled segmentation")
        for n in imported:
            check(n.GetAttribute(PRESET_ATTRIBUTE) is None, f"imported '{n.GetName()}' not touched by the watcher")
            check(n.GetSegmentation().GetNumberOfSegments() == 2, f"imported '{n.GetName()}' keeps its 2 segments")
        check(inst.guard.installed, "guard still installed after import")
    else:
        print("[smoke] SKIP scene import (set SLICER_PRESETS_TEST_MRB)")

    # 6) re-install is idempotent
    inst2 = slicer_presets.install()
    check(inst2 is not inst and slicer.modules.slicerPresets is inst2, "re-install replaces the previous installation")
except Exception:
    traceback.print_exc()
    failures.append("exception")

print(f"[smoke] {'OK' if not failures else 'FAILED: ' + '; '.join(failures)}")
slicer.app.exit(0 if not failures else 1)
