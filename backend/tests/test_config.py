import pytest
from pydantic import ValidationError

from backend.app.config import REQUIRED_CLASSES, RuntimeConfig, Zone
from backend.app.inference import map_classes
from backend.app.reporting import csv_safe
from backend.app.security import safe_filename


def test_all_classes_mapped_by_name_not_position():
    names = {9: "NO_HELMET", 5: "car", 2: "Motorbike", 14: "no_seat_belt", 44: "Seat_Belt", 12: "Helmet", 6: "SUV", 3: "minivan", 88: "person"}
    mapped, missing = map_classes(names)
    assert not missing
    assert mapped[9] == "No-Helmet"
    assert mapped[2] == "Bike"
    assert 88 not in mapped
    assert set(mapped.values()) == set(REQUIRED_CLASSES)


def test_coco_is_not_a_safety_model():
    mapped, missing = map_classes(["person", "bicycle", "car", "motorcycle", "bus", "truck"])
    assert mapped == {2: "Car", 3: "Bike"}
    assert "No-Seatbelt" in missing and "No-Helmet" in missing and "Jeep" in missing


@pytest.mark.parametrize("changes", [
    {"model_file": "../unsafe.pt"}, {"model_file": "C:\\model.pt"}, {"model_file": "http://example.test/a.pt"},
    {"imgsz": 641}, {"imgsz": 64}, {"frame_stride": 0}, {"min_votes": 9, "vote_window": 7},
    {"violation_confidence": .2, "confidence": .4}, {"track_low_thresh": .8, "track_high_thresh": .4},
    {"count_line": [[0, .5], [0, .5]]}, {"confidence": float('nan')},
])
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValidationError):
        RuntimeConfig(**changes)


@pytest.mark.parametrize("polygon", [[[0, 0], [1, 1], [0, 1], [1, 0]], [[0, 0], [0, 0], [0, 0]], [[-1, 0], [1, 0], [1, 1]]])
def test_invalid_zones_rejected(polygon):
    with pytest.raises(ValidationError):
        Zone(name="test", polygon=polygon)


def test_filename_safety():
    assert safe_filename("../../evil.mp4") == "evil.mp4"
    assert safe_filename("C:\\Users\\test\\road.mov") == "road.mov"
    assert '\r' not in safe_filename("bad\r\nname.mp4")
    assert len(safe_filename("a" * 500 + ".mp4")) <= 120


@pytest.mark.parametrize("value", ["=HYPERLINK('bad')", "+cmd", "-1+2", "@SUM(A1)", "  =bad"])
def test_csv_formula_injection(value):
    assert csv_safe(value).startswith("'")
