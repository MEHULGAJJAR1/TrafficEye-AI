import pytest

from evaluation.evaluate_associations import evaluate as decisions
from evaluation.evaluate_tracking import evaluate as tracking


def box(identity, x=100):
    return {'id': str(identity), 'class': 'Car', 'bbox': [x, 100, x+60, 200]}


def test_tracking_diagnostic_detects_id_switch():
    gt = {0: [box('gt-1')], 1: [box('gt-1', 103)], 2: [box('gt-1', 106)]}
    predicted = {0: [box(1)], 1: [box(1, 103)], 2: [box(2, 106)]}
    result = tracking(predicted, gt)
    assert result['identity_switches'] == 1
    assert result['box_match_precision'] == result['box_match_recall'] == 1
    assert result['mean_matched_iou'] == 1


def test_tracking_diagnostic_detects_miss_and_fragment():
    gt = {0: [box('gt-1')], 1: [box('gt-1')], 2: [box('gt-1')]}
    result = tracking({0: [box(1)], 2: [box(1)]}, gt)
    assert result['missed_observations'] == 1
    assert result['matched_track_fragmentations'] == 1


def test_association_accuracy_denominator_includes_reviewed_negatives():
    truth = {('job','1'): ('No-Helmet', 2), ('job','2'): ('none', 0), ('job','3'): ('No-Seatbelt', 5)}
    predicted = {('job','1'): ('No-Helmet', 2.5)}
    result = decisions(predicted, truth)
    assert result['true_positive_records'] == 1
    assert result['false_negative_records'] == 1
    assert result['true_negative_reviewed_identities'] == 1
    assert result['reviewed_identity_denominator'] == 3
    assert result['reviewed_identity_agreement'] == pytest.approx(2/3)


def test_wrong_type_or_mistimed_decision_is_not_counted_as_correct():
    result = decisions({('job','1'): ('No-Helmet', 15)}, {('job','1'): ('No-Helmet', 2)}, tolerance=2)
    assert result['true_positive_records'] == 0
    assert result['false_positive_records'] == result['false_negative_records'] == 1


def test_empty_ground_truth_is_rejected():
    with pytest.raises(ValueError):
        decisions({}, {})
    with pytest.raises(ValueError):
        tracking({}, {})


def test_tracking_export_cli_reads_actual_checkpointed_demo_results(client, tmp_path):
    import csv
    import json
    import subprocess
    import sys
    from backend.app.config import ROOT
    from conftest import complete_demo

    job = complete_demo(client, 3)
    output = tmp_path / 'predicted-tracks.csv'
    result = subprocess.run([sys.executable, str(ROOT / 'evaluation/export_tracks.py'), '--database', str(client.app.state.db.path), '--job-id', job['id'], '--output', str(output)], capture_output=True, text=True, timeout=20, cwd=ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'synthetic fixture tracks' in result.stdout
    with output.open(newline='') as file:
        rows = list(csv.DictReader(file))
    frames = client.app.state.db.query('SELECT payload FROM frames WHERE job_id=?', [job['id']])
    expected = sum(len(frame['payload']['tracks']) for frame in frames)
    assert len(rows) == expected > 0
    assert set(rows[0]) == {'frame','vehicle_id','vehicle_class','x1','y1','x2','y2'}
    assert 0 <= int(rows[0]['frame']) < 36
    assert float(rows[0]['x2']) > float(rows[0]['x1'])
