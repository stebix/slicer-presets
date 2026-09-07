"""Create and populate segmentation nodes from a :class:`~slicer_presets.spec.Preset`.

Only importable inside Slicer (needs the ``slicer`` module).
"""

from __future__ import annotations

import logging
import re

import slicer

from .spec import Preset, SegmentSpec

log = logging.getLogger("slicer_presets")

#: Node attribute recording which preset populated a segmentation node.
PRESET_ATTRIBUTE = "SlicerPresets.Preset"

#: Names Slicer gives to segments it creates on its own ("Segment_1", ...).
DEFAULT_SEGMENT_NAME_RE = re.compile(r"^Segment_\d+$")

BINARY_LABELMAP = "Binary labelmap"


def segment_is_empty(segment) -> bool:
    """True if the segment has no voxels in its binary labelmap representation."""
    rep = segment.GetRepresentation(BINARY_LABELMAP)
    if rep is None:
        return True
    try:
        x0, x1, y0, y1, z0, z1 = rep.GetExtent()
    except (AttributeError, TypeError, ValueError):
        return False
    if x0 > x1 or y0 > y1 or z0 > z1:
        return True
    try:
        return rep.GetScalarRange()[1] <= 0
    except (AttributeError, TypeError):
        return False


def only_default_empty_segments(node) -> bool:
    """True if the node holds no segments other than empty ``Segment_N`` placeholders."""
    segmentation = node.GetSegmentation()
    for i in range(segmentation.GetNumberOfSegments()):
        segment = segmentation.GetNthSegment(i)
        if not (DEFAULT_SEGMENT_NAME_RE.match(segment.GetName() or "") and segment_is_empty(segment)):
            return False
    return True


def _find_existing(segmentation, spec: SegmentSpec) -> str | None:
    if spec.segment_id and segmentation.GetSegment(spec.segment_id) is not None:
        return spec.segment_id
    segment_id = segmentation.GetSegmentIdBySegmentName(spec.name)
    return segment_id or None


def _configure(segment, spec: SegmentSpec) -> None:
    segment.SetName(spec.name)
    segment.SetColor(*spec.color)
    if spec.label_value is not None and hasattr(segment, "SetLabelValue"):
        segment.SetLabelValue(int(spec.label_value))
    if spec.terminology:
        try:
            segment.SetTag(slicer.vtkSegment.GetTerminologyEntryTagName(), spec.terminology)
        except Exception:  # older builds without the static helper
            segment.SetTag("TerminologyEntry", spec.terminology)


def apply_preset(node, preset: Preset, *, update_existing: bool = True, adopt_default_segments: bool = True) -> dict[str, list[str]]:
    """Make ``node`` contain the preset's segments.

    * Segments that already exist (matched by ``id`` or name) are updated in place
      when ``update_existing`` is set, otherwise left alone.
    * Empty placeholder segments (``Segment_N``) are re-purposed in order for the
      preset entries when ``adopt_default_segments`` is set, so the segment the
      Segment Editor just created and selected becomes preset segment #1.
    * Everything else is added as a new empty segment.

    Returns the segment IDs grouped as ``{"added", "updated", "adopted"}``.
    """
    segmentation = node.GetSegmentation()
    spare: list[str] = []
    if adopt_default_segments:
        for i in range(segmentation.GetNumberOfSegments()):
            segment = segmentation.GetNthSegment(i)
            if DEFAULT_SEGMENT_NAME_RE.match(segment.GetName() or "") and segment_is_empty(segment):
                spare.append(segmentation.GetNthSegmentID(i))

    result: dict[str, list[str]] = {"added": [], "updated": [], "adopted": []}
    for spec in preset.segments:
        segment_id = _find_existing(segmentation, spec)
        if segment_id is not None:
            if not update_existing:
                continue
            result["updated"].append(segment_id)
        elif spare:
            segment_id = spare.pop(0)
            result["adopted"].append(segment_id)
        else:
            segment_id = segmentation.AddEmptySegment(spec.requested_id, spec.name)
            result["added"].append(segment_id)
        _configure(segmentation.GetSegment(segment_id), spec)

    node.SetAttribute(PRESET_ATTRIBUTE, preset.name)
    return result


def current_source_volume(scene=None):
    """A reasonable reference volume: the Segment Editor's, else the first scalar volume."""
    scene = scene or slicer.mrmlScene
    return scene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")


def create_segmentation(preset: Preset, *, name: str | None = None, reference_volume=None, scene=None):
    """Add a new segmentation node pre-filled with the preset segments."""
    scene = scene or slicer.mrmlScene
    node = scene.AddNewNodeByClass("vtkMRMLSegmentationNode", name or preset.node_name)
    node.CreateDefaultDisplayNodes()
    if reference_volume is not None:
        node.SetReferenceImageGeometryParameterFromVolumeNode(reference_volume)
    apply_preset(node, preset)
    return node


def scene_has_segmentation(scene=None) -> bool:
    scene = scene or slicer.mrmlScene
    return scene.GetNumberOfNodesByClass("vtkMRMLSegmentationNode") > 0


def show_in_segment_editor(node, source_volume=None) -> None:
    """Open the Segment Editor on ``node`` (GUI only)."""
    if slicer.app.commandOptions().noMainWindow:
        return
    slicer.util.selectModule("SegmentEditor")
    widget = slicer.modules.segmenteditor.widgetRepresentation().self()
    widget.editor.setSegmentationNode(node)
    if source_volume is None and not widget.editor.sourceVolumeNodeID():
        source_volume = current_source_volume()
    if source_volume is not None:
        widget.editor.setSourceVolumeNode(source_volume)
