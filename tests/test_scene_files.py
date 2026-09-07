import zipfile

import pytest

from slicer_presets import scene_files

SCENE = """<MRML version="Slicer5" userTags="">
 <Segmentation id="vtkMRMLSegmentationNode1" name="Segmentation" ></Segmentation>
 <SegmentEditor
  id="vtkMRMLSegmentEditorNodeSegmentEditor" name="SegmentEditor" singletonTag="SegmentEditor" attributes="BrushSphere:1;Islands.Operation:KEEP_LARGEST_ISLAND" references="masterVolumeRef:vtkMRMLScalarVolumeNode1;segmentationRef:vtkMRMLSegmentationNode1;" selectedSegmentID="2.25.2012" activeEffectName="Islands" maskMode="EditAllowedEverywhere" maskSegmentID="" overwriteMode="OverwriteAllSegments" ></SegmentEditor>
 <SegmentationStorage id="vtkMRMLSegmentationStorageNode1" fileName="Data/Segmentation.seg.nrrd" ></SegmentationStorage>
</MRML>
"""


def test_active_effect_mode_strips_only_the_effect():
    out, n = scene_files.sanitize_mrml_text(SCENE)
    assert n == 1
    assert "activeEffectName" not in out
    assert 'selectedSegmentID="2.25.2012"' in out
    assert 'attributes="BrushSphere:1;Islands.Operation:KEEP_LARGEST_ISLAND"' in out
    assert "<SegmentationStorage" in out and "<Segmentation " in out
    assert scene_files.sanitize_mrml_text(out) == (out, 0)  # idempotent


def test_selection_and_node_modes():
    out, n = scene_files.sanitize_mrml_text(SCENE, "selection")
    assert n == 3
    for attr in ("activeEffectName", "selectedSegmentID", "maskSegmentID"):
        assert attr not in out
    assert "<SegmentEditor" in out

    out, n = scene_files.sanitize_mrml_text(SCENE, "node")
    assert n == 1 and "<SegmentEditor" not in out and "SegmentationStorage" in out

    with pytest.raises(ValueError):
        scene_files.sanitize_mrml_text(SCENE, "bogus")


def test_attributes_outside_segment_editor_node_untouched():
    text = SCENE.replace("<Segmentation id=", '<Segmentation activeEffectName="keep" id=')
    out, n = scene_files.sanitize_mrml_text(text)
    assert n == 1 and 'activeEffectName="keep"' in out


def _make_mrb(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("scene/scene.mrml", SCENE, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("scene/Data/Segmentation.seg.nrrd", b"NRRD0004\n", compress_type=zipfile.ZIP_STORED)
        z.writestr("scene/scene.png", b"\x89PNG", compress_type=zipfile.ZIP_STORED)


def test_sanitize_mrb_roundtrip(tmp_path):
    src = tmp_path / "case.mrb"
    _make_mrb(src)
    assert scene_files.needs_sanitizing(src)

    out, n = scene_files.sanitize_scene_file(src)
    assert out == tmp_path / "case.safe.mrb" and n == 1
    assert not scene_files.needs_sanitizing(out)
    with zipfile.ZipFile(out) as z:
        names = [i.filename for i in z.infolist()]
        assert names == ["scene/scene.mrml", "scene/Data/Segmentation.seg.nrrd", "scene/scene.png"]
        assert z.getinfo("scene/scene.mrml").compress_type == zipfile.ZIP_DEFLATED
        assert z.getinfo("scene/scene.png").compress_type == zipfile.ZIP_STORED
        assert z.read("scene/Data/Segmentation.seg.nrrd") == b"NRRD0004\n"
        assert "activeEffectName" not in z.read("scene/scene.mrml").decode()

    with pytest.raises(ValueError):
        scene_files.sanitize_mrb(src, src)


def test_sanitize_mrml_file_and_dispatch(tmp_path):
    mrml = tmp_path / "s.mrml"
    mrml.write_text(SCENE, encoding="utf-8")
    out, n = scene_files.sanitize_scene_file(mrml, tmp_path / "out.mrml", "node")
    assert n == 1 and "<SegmentEditor" not in out.read_text(encoding="utf-8")
    assert not scene_files.needs_sanitizing(tmp_path / "other.nrrd")
    with pytest.raises(ValueError):
        scene_files.sanitize_scene_file(tmp_path / "x.nrrd")
