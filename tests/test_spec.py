import json
from pathlib import Path

import pytest

from slicer_presets import spec
from slicer_presets.spec import SpecError, load_spec_file, parse_color, parse_spec, select_preset

REPO = Path(__file__).resolve().parent.parent

LEGACY = {
    "name": "InnerEar",
    "segments": [
        {"name": "Cochlea", "order": 1, "labelValue": 2, "color": "#3CB44B"},
        {"name": "Vestibule", "order": 0, "labelValue": 1, "color": "#E6194B"},
    ],
}


def test_parse_color_variants():
    assert parse_color("#FF0000") == (1.0, 0.0, 0.0)
    assert parse_color("00ff00") == (0.0, 1.0, 0.0)
    assert parse_color([0.5, 0.25, 1]) == (0.5, 0.25, 1.0)
    assert parse_color([255, 0, 51]) == pytest.approx((1.0, 0.0, 0.2))
    for bad in ("#12345", "red", [1, 2], [-1, 0, 0], [300, 0, 0], None):
        with pytest.raises(SpecError):
            parse_color(bad)


def test_legacy_single_preset_layout_and_order():
    f = parse_spec(LEGACY)
    assert f.names == ["InnerEar"] and f.default == "InnerEar"
    p = f.presets["InnerEar"]
    assert [s.name for s in p.segments] == ["Vestibule", "Cochlea"]  # sorted by "order"
    assert [s.label_value for s in p.segments] == [1, 2]
    assert p.options == spec.PresetOptions()
    assert p.node_name == "InnerEar"


def test_multi_preset_layout_merges_file_options():
    data = {
        "version": 1,
        "default": "B",
        "options": {"createOnStartup": True, "nodeName": "Seg"},
        "presets": [
            {"name": "A", "segments": [{"name": "x", "color": "#000000"}]},
            {"name": "B", "segments": [{"name": "y", "color": "#000000", "id": "why"}], "options": {"createOnStartup": False}},
        ],
    }
    f = parse_spec(data)
    assert f.default == "B"
    assert f.presets["A"].options.create_on_startup is True
    assert f.presets["A"].node_name == "Seg"
    assert f.presets["B"].options.create_on_startup is False
    assert f.presets["B"].segments[0].requested_id == "why"
    assert f.presets["B"].segments[0].label_value is None


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d.__setitem__("segments", []), "non-empty list"),
        (lambda d: d["segments"].append({"name": "Cochlea", "labelValue": 3, "color": "#000000"}), "duplicate segment name"),
        (lambda d: d["segments"].append({"name": "Other", "labelValue": 1, "color": "#000000"}), "duplicate labelValue"),
        (lambda d: d["segments"].append({"name": "Other", "color": "#000000"}), "for all segments or for none"),
        (lambda d: d["segments"][0].__setitem__("labelValue", 0), "positive integer"),
        (lambda d: d["segments"][0].__setitem__("labelValue", True), "positive integer"),
        (lambda d: d["segments"][0].pop("name"), "non-empty string"),
        (lambda d: d.__setitem__("options", {"applyToNewSegmentation": True}), "unknown key"),
        (lambda d: d.__setitem__("options", {"sceneGuard": "yes"}), "expected bool"),
        (lambda d: d.__setitem__("version", 2), "unsupported version"),
    ],
)
def test_validation_errors(mutate, message):
    data = json.loads(json.dumps(LEGACY))
    mutate(data)
    with pytest.raises(SpecError, match=message):
        parse_spec(data)


def test_default_must_exist_and_names_unique():
    with pytest.raises(SpecError, match="default preset"):
        parse_spec({"default": "Z", "presets": [{"name": "A", "segments": [{"name": "x", "color": "#000000"}]}]})
    with pytest.raises(SpecError, match="duplicate preset name"):
        parse_spec({"presets": [{"name": "A", "segments": [{"name": "x", "color": "#000000"}]}] * 2})


def test_select_preset_precedence(monkeypatch):
    f = parse_spec({"default": "A", "presets": [
        {"name": "A", "segments": [{"name": "x", "color": "#000000"}]},
        {"name": "B", "segments": [{"name": "y", "color": "#000000"}]},
    ]})
    assert select_preset(f).name == "A"
    monkeypatch.setenv(spec.ENV_PRESET, "B")
    assert select_preset(f).name == "B"
    assert select_preset(f, "A").name == "A"
    with pytest.raises(SpecError, match="not found"):
        select_preset(f, "C")


def test_load_spec_file_errors(tmp_path):
    with pytest.raises(SpecError, match="not found"):
        load_spec_file(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(SpecError, match="invalid JSON"):
        load_spec_file(bad)


def test_default_spec_path(monkeypatch, tmp_path):
    monkeypatch.delenv(spec.ENV_SPEC, raising=False)
    monkeypatch.delenv(spec.ENV_HOME, raising=False)
    assert spec.default_spec_path() == REPO / "presets" / "default.json"
    assert spec.default_spec_path(tmp_path) == tmp_path / "presets" / "default.json"
    monkeypatch.setenv(spec.ENV_HOME, str(tmp_path / "h"))
    assert spec.default_spec_path() == tmp_path / "h" / "presets" / "default.json"
    monkeypatch.setenv(spec.ENV_SPEC, str(tmp_path / "s.json"))
    assert spec.default_spec_path() == tmp_path / "s.json"


def test_shipped_default_spec_is_valid():
    f = load_spec_file(REPO / "presets" / "default.json")
    p = select_preset(f)
    assert p.name == "InnerEar"
    assert [s.label_value for s in p.segments] == [1, 2, 3, 4, 5]
    assert p.options.create_on_startup is False
    assert p.options.open_segment_editor is False
    assert p.options.scene_guard is True
