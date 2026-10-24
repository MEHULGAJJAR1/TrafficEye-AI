"""Measure violation decisions against human-adjudicated vehicle identities (including negatives).

Prediction CSV: app's violations export.
Ground truth CSV: job_id,vehicle_id,violation_type,video_time_seconds
violation_type is No-Helmet, No-Seatbelt, or none. Label every identity under review;
this measures decisions for fixed identities, NOT the correctness of the tracker itself.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

VALID = {'No-Helmet', 'No-Seatbelt', 'none'}


def read_decisions(path, ground_truth=False):
    result = {}
    with Path(path).open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            key = (row['job_id'], row['vehicle_id'])
            label = row['violation_type'] or 'none'
            if label not in VALID:
                raise ValueError(f'Unknown violation label: {label}')
            if key in result:
                raise ValueError('This diagnostic evaluator accepts one adjudicated safety type per vehicle identity. Split separate tasks if needed.')
            result[key] = (label, float(row.get('video_time_seconds') or 0))
            if not ground_truth and row.get('source_mode') == 'demo':
                raise ValueError('Scripted demo rows are not eligible for a real association-accuracy evaluation.')
    return result


def evaluate(predictions, truth, tolerance=2.):
    if not truth:
        raise ValueError('Ground truth must include positive and/or negative reviewed identities.')
    tp = fp = fn = tn = agreed = 0
    for key in set(predictions) | set(truth):
        predicted, pt = predictions.get(key, ('none', 0.))
        expected, gt = truth.get(key, ('none', 0.))
        matched = predicted == expected and (expected == 'none' or abs(pt - gt) <= tolerance)
        if expected != 'none':
            if matched:
                tp += 1
            else:
                fn += 1
                if predicted != 'none':
                    fp += 1
        elif predicted != 'none':
            fp += 1
        elif key in truth:
            tn += 1
        if key in truth and matched:
            agreed += 1
    return {'true_positive_records': tp, 'false_positive_records': fp, 'false_negative_records': fn, 'true_negative_reviewed_identities': tn, 'precision': tp / (tp + fp) if tp + fp else 0., 'recall': tp / (tp + fn) if tp + fn else 0., 'reviewed_identity_agreement': agreed / len(truth), 'reviewed_identity_denominator': len(truth), 'timestamp_tolerance_seconds': tolerance, 'notes': ['Unmatched or wrong-type predictions count as false positives; a wrong-type/mistimed positive also misses the expected positive.', 'Agreement denominator is ALL manually reviewed GT identities, including explicit none rows.', 'A prediction on an unreviewed identity is conservatively counted as a false positive; provide complete adjudication.', 'This conditions on the supplied identity mapping. It is not end-to-end real-world identity accuracy.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--ground-truth', type=Path, required=True)
    parser.add_argument('--tolerance', type=float, default=2.)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'results/associations.json')
    args = parser.parse_args()
    if args.tolerance < 0:
        parser.error('--tolerance must be nonnegative.')
    result = evaluate(read_decisions(args.predictions), read_decisions(args.ground_truth, True), args.tolerance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
