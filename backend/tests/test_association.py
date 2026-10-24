import numpy as np
import pytest

from backend.app.association import ViolationEngine
from backend.app.config import RuntimeConfig, Zone
from backend.app.inference import Detection
from backend.app.tracking import BoTSortTracker, DemoTracker


def vehicle(tid=1, bbox=None, name="Bike"):
    return Detection(name, .95, bbox or [100, 100, 150, 210], tid)


def safety(name="No-Helmet", bbox=None, conf=.9):
    return Detection(name, conf, bbox or [112, 80, 135, 105])


def test_temporal_voting_and_duplicate_prevention():
    engine = ViolationEngine(RuntimeConfig())
    records = []
    for i in range(20):
        _, created, _ = engine.update([vehicle()], [safety()], 960, 540, i / 12)
        if i < 3:
            assert not created
        records += created
    assert len(records) == 1
    assert records[0]["track_id"] == 1
    assert records[0]["votes"] >= 4
    assert records[0]["confidence"] == .9


def test_unknown_low_confidence_and_missing_boxes_are_not_violations():
    engine = ViolationEngine(RuntimeConfig())
    for i in range(12):
        tracks, records, _ = engine.update([vehicle()], [safety(conf=.5)] if i % 2 else [], 960, 540, i / 12)
        assert not records
        assert tracks[0]["helmet_status"] == "unknown"


def test_conflicting_safety_labels_are_unknown():
    engine = ViolationEngine(RuntimeConfig())
    for i in range(12):
        tracks, records, _ = engine.update([vehicle()], [safety(), safety("Helmet", conf=.89)], 960, 540, i / 12)
        assert not records
        assert tracks[0]["helmet_status"] == "unknown"


def test_ambiguous_two_motorcycles_are_not_forced():
    engine = ViolationEngine(RuntimeConfig())
    for i in range(12):
        _, records, _ = engine.update([vehicle(1), vehicle(2, [104, 104, 154, 214])], [safety()], 960, 540, i / 12)
        assert not records


def test_seatbelt_is_never_assigned_to_motorcycle():
    engine = ViolationEngine(RuntimeConfig())
    for i in range(12):
        _, records, _ = engine.update([vehicle()], [safety("No-Seatbelt", [110, 110, 135, 140])], 960, 540, i / 12)
        assert not records


def test_helmet_associated_to_correct_bike_not_nearby_car():
    engine = ViolationEngine(RuntimeConfig())
    records = []
    for i in range(8):
        _, created, _ = engine.update([vehicle(), vehicle(2, [180, 90, 250, 220], "Car")], [safety()], 960, 540, i / 12)
        records.extend(created)
    assert len(records) == 1 and records[0]["track_id"] == 1


def test_positive_evidence_does_not_create_record():
    engine = ViolationEngine(RuntimeConfig())
    for i in range(8):
        tracks, records, _ = engine.update([vehicle()], [safety("Helmet")], 960, 540, i / 12)
        assert not records
    assert tracks[0]["helmet_status"] == "Helmet"


def test_outside_zone_has_no_violation_or_count():
    cfg = RuntimeConfig(zones=[Zone(name="right", polygon=[(.5, 0), (1, 0), (1, 1), (.5, 1)])])
    engine = ViolationEngine(cfg)
    for i in range(8):
        tracks, records, crossings = engine.update([vehicle()], [safety()], 960, 540, i / 12)
        assert not records and not crossings
        assert tracks[0]["zone"] == "outside"


def test_direction_counting_and_once_per_direction():
    engine = ViolationEngine(RuntimeConfig(count_line=[(0, .5), (1, .5)]))
    crossings = []
    for i, bottom in enumerate([200, 240, 300, 340, 240, 200, 300, 320]):
        _, _, created = engine.update([vehicle(bbox=[100, bottom-80, 150, bottom])], [], 960, 540, i * .1)
        crossings += created
    assert [v["direction"] for v in crossings] == ["IN", "OUT"]


def test_crossing_outside_finite_line_not_counted():
    engine = ViolationEngine(RuntimeConfig(count_line=[(.5, .5), (.9, .5)]))
    crossings = []
    for i, bottom in enumerate([200, 300]):
        _, _, created = engine.update([vehicle(bbox=[50, bottom-80, 90, bottom])], [], 960, 540, i * .1)
        crossings += created
    assert not crossings


def test_small_vehicle_no_safety_decision():
    engine = ViolationEngine(RuntimeConfig())
    for i in range(8):
        _, records, _ = engine.update([vehicle(bbox=[100, 100, 112, 130])], [safety(bbox=[101, 98, 110, 107])], 960, 540, i / 12)
        assert not records


def test_demo_tracker_recovers_same_id_after_gap():
    tracker = DemoTracker(RuntimeConfig())
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    first = tracker.update([vehicle(tid=None)], frame)[0].track_id
    tracker.update([], frame)
    recovered = tracker.update([vehicle(tid=None, bbox=[102, 103, 152, 213])], frame)[0].track_id
    assert first == recovered


def test_real_botsort_runs_and_keeps_persistent_vehicle_id():
    tracker = BoTSortTracker(RuntimeConfig(gmc_method="none"))
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    ids = []
    for i in range(5):
        output = tracker.update([vehicle(tid=None, bbox=[100 + i*3, 100, 160 + i*3, 220]), safety()], frame)
        assert len(output) == 1
        ids.append(output[0].track_id)
    assert len(set(ids)) == 1


@pytest.mark.parametrize('fps', [12, 25, 30, 60, 120, 240])
def test_evidence_maturity_is_not_impossible_at_normal_or_high_frame_rates(fps):
    engine = ViolationEngine(RuntimeConfig())
    confirmations = []
    for i in range(int(fps / 2) + 1):
        timestamp = i / fps
        _, records, _ = engine.update([vehicle()], [safety()], 960, 540, timestamp)
        if timestamp < .25 - 1e-9:
            assert not records
        confirmations += records
    assert len(confirmations) == 1
    assert confirmations[0]['votes'] >= 4
    assert confirmations[0]['confidence'] == .9


def test_insufficient_window_support_resets_temporal_maturity():
    engine = ViolationEngine(RuntimeConfig())
    found = []
    for i in range(42):
        # Brief initial support, a full unknown window, then stable new evidence.
        objects = [safety()] if i < 10 or i >= 18 else []
        timestamp = i / 60
        _, records, _ = engine.update([vehicle()], objects, 960, 540, timestamp)
        if timestamp < 18 / 60 + .25 - 1e-9:
            assert not records
        found += records
    assert len(found) == 1
