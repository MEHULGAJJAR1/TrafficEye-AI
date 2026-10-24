"""Transparent frame-level tracking stability measurements against manually labelled identities.

Both CSVs: frame,vehicle_id,vehicle_class,x1,y1,x2,y2. Same frame sampling and class taxonomy.
This is a small diagnostic evaluator, NOT an implementation of HOTA/official TrackEval IDF1.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.tracking import iou


def read_boxes(path):
    result = defaultdict(list)
    seen = set()
    with Path(path).open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            frame, identity = int(row['frame']), row['vehicle_id']
            bbox = [float(row[k]) for k in ('x1', 'y1', 'x2', 'y2')]
            if frame < 0 or not np.isfinite(bbox).all() or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                raise ValueError('Every frame and bounding box must be valid and finite.')
            if (frame, identity) in seen:
                raise ValueError('An identity can appear only once in a frame.')
            seen.add((frame, identity))
            result[frame].append({'id': identity, 'class': row['vehicle_class'], 'bbox': bbox})
    return result


def evaluate(predictions, truth, threshold=.5):
    if not truth or not sum(len(v) for v in truth.values()):
        raise ValueError('The ground-truth file contains no labelled boxes.')
    tp = fp = fn = switches = fragments = 0
    overlaps = []
    previous_id, previously_matched, matched_once = {}, {}, set()
    for frame in sorted(set(predictions) | set(truth)):
        gt, pred = truth.get(frame, []), predictions.get(frame, [])
        costs = np.ones((len(gt), len(pred)), dtype=float)
        for i, g in enumerate(gt):
            for j, p in enumerate(pred):
                if g['class'] == p['class']:
                    score = iou(g['bbox'], p['bbox'])
                    if score >= threshold:
                        # Invalid pairs have a large cost so assignment maximizes valid match count first.
                        costs[i, j] = (1 - score) / max(1, len(gt) + len(pred))
        assignments = linear_sum_assignment(costs) if gt and pred else ([], [])
        matches = [(i, j) for i, j in zip(*assignments) if costs[i, j] < 1]
        matched_gt = set()
        for i, j in matches:
            g, p = gt[i], pred[j]
            matched_gt.add(g['id'])
            overlaps.append(iou(g['bbox'], p['bbox']))
            if g['id'] in previous_id and previous_id[g['id']] != p['id']:
                switches += 1
            if g['id'] in matched_once and previously_matched.get(g['id']) is False:
                fragments += 1
            previous_id[g['id']] = p['id']
            previously_matched[g['id']] = True
            matched_once.add(g['id'])
        for g in gt:
            if g['id'] not in matched_gt:
                previously_matched[g['id']] = False
        tp += len(matches)
        fp += len(pred) - len(matches)
        fn += len(gt) - len(matches)
    gt_count = tp + fn
    return {'ground_truth_observations': gt_count, 'matched_observations': tp, 'false_positive_observations': fp, 'missed_observations': fn, 'box_match_precision': tp / (tp + fp) if tp + fp else 0., 'box_match_recall': tp / gt_count, 'identity_switches': switches, 'matched_track_fragmentations': fragments, 'mean_matched_iou': float(np.mean(overlaps)) if overlaps else 0., 'MOTA_diagnostic': 1 - (fn + fp + switches) / gt_count, 'iou_threshold': threshold, 'definition': 'Class-aware, per-frame Hungarian IoU matching. Identity switches compare the last matched predicted ID for each GT identity; fragmentation is a matched→unmatched-labelled→matched transition. Not HOTA or official TrackEval IDF1.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--ground-truth', type=Path, required=True)
    parser.add_argument('--iou', type=float, default=.5)
    parser.add_argument('--output', type=Path, default=ROOT / 'evaluation/results/tracking.json')
    args = parser.parse_args()
    if not 0 < args.iou <= 1:
        parser.error('--iou must lie in (0, 1].')
    result = evaluate(read_boxes(args.predictions), read_boxes(args.ground_truth), args.iou)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
