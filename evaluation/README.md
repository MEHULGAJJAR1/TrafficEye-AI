# Evaluation: only report what the data supports

No suitable real-world labelled traffic validation set or trained custom weights were supplied. These scripts are functional tools, not pre-filled benchmark reports. Tests use original synthetic fixtures/randomly initialized weights to check execution and serialization; those results must not be interpreted as traffic accuracy.

## 1. Detection validation

Install full requirements. Supply a trusted YOLO26 detection checkpoint with the required eight class names and a trusted dataset YAML with a genuinely labelled `val` split:

```powershell
.\.venv\Scripts\python.exe evaluation\evaluate_model.py `
  --weights .\models\traffic-custom.pt `
  --data .\your-labelled-data.yaml `
  --device cpu --imgsz 640 --batch 4 `
  --output .\evaluation\results\detection
```

Output:

- `metrics.json`: genuine precision, recall, mAP@0.5, mAP@0.5:0.95, per-class results, numeric confusion matrix, axis labels and measured per-image speeds.
- `validation/confusion_matrix.png`, normalized matrix and available PR/F1/precision/recall curves and labelled-batch plots from Ultralytics.
- Undefined/non-finite numbers are `null`; no made-up metrics are substituted. Plot artifacts depend on validation data and Ultralytics' supported output for that task.

The script captures the actual validator using Ultralytics' custom-validator hook; it does not assume a nonexistent `model.validator` attribute. It converts NumPy scalar types before JSON serialization. COCO-style extra evaluation is not silently requested (`save_json=False`), so the unrelated faster-coco-eval auto-install is not needed for this report. First-time plotting may fetch an upstream font.

Use camera/sequence-level train/validation/test splits, not adjacent frames spread across splits. Include rare classes, negatives, challenging conditions and accurate safety-region annotation. A class schema match alone is not validation.

## 2. Export predicted tracking boxes

From the project root, preferably after processing is complete and while no writes are occurring:

```powershell
$JobId = Read-Host 'Job UUID from the application'
.\.venv\Scripts\python.exe evaluation\export_tracks.py `
  --database .\data\trafficeye.sqlite3 --job-id $JobId `
  --output .\evaluation\results\predicted-tracks.csv
```

Format (pixel coordinates in original source dimensions):

```csv
frame,vehicle_id,vehicle_class,x1,y1,x2,y2
```

Frames are zero-based **source frame indices**. If stride > 1, annotate/use the same sampled frames in ground truth. Ground-truth identities can have different IDs from predictions; matching is class-aware Hungarian assignment with an IoU threshold.

## 3. Tracking stability with ground truth

Create a separate fully labelled CSV in the same format, with stable ground-truth identities. Then:

```powershell
.\.venv\Scripts\python.exe evaluation\evaluate_tracking.py `
  --predictions .\evaluation\results\predicted-tracks.csv `
  --ground-truth .\your-ground-truth-tracks.csv --iou 0.5
```

Reports matched/missed/false-positive box observations, box-match precision/recall, identity switches, matched-track fragmentation, mean matched IoU and a diagnostic MOTA formula. Switches compare each GT identity's last matched prediction ID; a matched → unmatched-labelled → matched transition is a fragmentation. This small evaluator is **not official TrackEval, HOTA or IDF1** and should not be presented as those metrics.

Predictions in unlabelled frames count as false positives, so ground truth must be complete for the reviewed sampled interval. Same class definitions and image dimensions are required.

## 4. Violation/association decision evaluation

Download the application's **violations CSV** for a real-inference job. Manually adjudicate **every reviewed vehicle identity**, including negatives, using that same `(job_id, vehicle_id)` mapping:

```csv
job_id,vehicle_id,violation_type,video_time_seconds
```

`violation_type`: `No-Helmet`, `No-Seatbelt`, or `none`. For a positive, label a video time within the event's decision window; choose an appropriate tolerance. Negative rows use time 0. One adjudicated safety task/type per identity is accepted; split tasks if necessary.

```powershell
.\.venv\Scripts\python.exe evaluation\evaluate_associations.py `
  --predictions .\downloaded-violations.csv `
  --ground-truth .\your-adjudicated-decisions.csv --tolerance 2
```

Reports TP/FP/FN records, reviewed-negative TN identities, precision, recall and reviewed-identity decision/timestamp agreement. Wrong type or out-of-tolerance time misses the expected positive and also creates a false positive. Unreviewed predictions are conservatively false positives. Agreement denominator is all manually reviewed ground-truth identities, including explicit none rows.

This conditions on fixed adjudicated tracker identities; it **does not** measure end-to-end physical identity or prove correct driver/rider assignment. Evaluate tracker identity mapping separately. The script rejects `source_mode=demo` rows to prevent scripted data from being reported as real association accuracy.

## 5. Performance measurements

- API job `processing_fps`: sampled frames / active wall time, including decode, tracking, rules, SQLite and JPEG work, excluding pause time.
- API job `inference_fps`: sampled frames / cumulative model-call time; zero in demo because no model ran.
- API job `elapsed`: active wall seconds; `processed_frames`: analyzed samples, `decoded_frames`: source reads, `target_frames`: metadata-based source target.
- Validation `speed_ms_per_image`: Ultralytics' measured preprocessing/inference/postprocessing timings. Its FPS equivalent is not full-video throughput.

Report hardware, OS, Python/torch/CUDA versions, model variant, warmup, image size, stride, batch, CPU thread count, codec and evidence frequency with any benchmark. Do not compare the deliberately throttled scripted demo to real inference. No CUDA or real traffic accuracy benchmark was possible in this CPU-only delivery without the required trained data/model.
