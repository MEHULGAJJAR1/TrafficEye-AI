# Model, annotation and safety guide

## What must be supplied

1. A trusted, trained **Ultralytics YOLO26 axis-aligned detection .pt checkpoint**, containing all eight required class names/semantics.
2. Legally obtained camera footage with sufficient resolution and a suitable viewpoint for the relevant safety objects.
3. For real evaluation: a representative, independently labelled validation/test dataset, including negatives, occlusion/lighting variation and camera-specific conditions. Split by camera/sequence to avoid near-duplicate frame leakage.
4. Optional supported GPU hardware/driver and matching PyTorch wheels for practical throughput. CPU is supported; real-time CPU performance is not promised.

No custom-trained weights or real traffic labels were supplied for this release. The official COCO YOLO26 smoke run validates only generic CPU inference and missing-class rejection. Tests using random eight-class weights validate software protocols, not safety accuracy.

## Required taxonomy and name mapping

`Bike, Car, Jeep, Van, Helmet, No-Helmet, Seatbelt, No-Seatbelt` in any numeric order. Read your actual `model.names`. Normalized aliases in `config/class_aliases.yaml` are deliberate: Motorcycle/Motorbike → Bike, SUV → Jeep, Minivan → Van and common safety-name punctuation/wording. Review whether SUV/Jeep/Van semantics genuinely match your dataset before enabling them. Unrecognized classes are ignored; any missing required canonical class blocks real jobs.

Do not map `person`, `rider`, `truck`, `bus` or `bicycle` to missing classes. Do not rename the class list on a stock checkpoint and call it trained. Schema validation cannot verify training quality.

## Annotation assumptions

- Vehicle boxes describe the visible motorcycle/car/Jeep/Van body consistently. Only vehicles enter the tracker and unique-vehicle analytics.
- Helmet / No-Helmet boxes should localize the relevant visible rider/head region, not the whole image. The Bike association region expands above the body box.
- Seatbelt / No-Seatbelt boxes must consistently localize a visible driver/cabin/upper-body region that matches your training protocol. Absence of a visible belt box is **not** sufficient evidence for No-Seatbelt. Explicit negative-class predictions are required.
- The current association rule uses upper vehicle/cabin geometry. It does not have a driver detector, pose estimation, per-person identities or passenger-role verification. Multiple riders/passengers, overlaps and odd viewpoints can invalidate an otherwise high-confidence association.
- Very small vehicles, near-tied spatial candidates, low-confidence safety boxes and close contradictory safety predictions are treated as unknown. Unknown is not compliance.

## Decision-rule tuning

Minimum votes and ratios are across processed observations, including unknowns. A current supporting observation and minimum video-time maturity are also required. Maturity persists across consecutive qualifying rolling windows and resets when vote count/ratio is insufficient; it is not limited to the duration of N frames at high FPS. Frame skipping changes the temporal sampling and tracker motion, so calibrate it jointly with the buffer, voting window and minimum evidence span. Multiple highly correlated frames are not independent proof.

The default full-frame zone and line are examples, not a deployment calibration. Draw zones to exclude pavements/other lanes/irrelevant views; use normalized polygons and a finite counting line appropriate to the camera. Count direction is geometric relative to the line orientation, not a learned traffic heading.

Duplicate prevention is unique by job/track/type, with a short high-IoU cooldown for new fragments. It can still miss duplicates after long occlusions or suppress truly distinct overlapping vehicles. Tracking identities are not physical/person/registration identities. Human review must consider these failure modes.

## Example dataset YAML

Use `config/dataset.example.yaml` as a schema reference and replace its explicitly marked path with your actual dataset root. YOLO labels are one `class_id x_center y_center width height` line per object, normalized to the image. The required names may be in any consistent ID order in the model/dataset; do not assume the example order matches an existing model.

An existing trusted eight-class training workflow may use Ultralytics' official training interface. This project does not invent a dataset, training result or validated weights. Consult the upstream documentation and licensing before training/deployment.

## Validation and performance

`evaluation/evaluate_model.py` uses actual Ultralytics validation, captures its real confusion matrix through the documented custom-validator hook and serializes NumPy scalar types safely. Missing/undefined numeric values are represented as null rather than invented numbers. It writes precision, recall, mAP@0.5, mAP@0.5:0.95, per-class metrics, numeric matrix and plots. The CLI refuses absent weights/data or incomplete class schemas.

`evaluation/evaluate_tracking.py` measures matching precision/recall, identity switches, fragmentation and mean matched IoU against manually labelled tracks. It is not official TrackEval/HOTA/IDF1. `evaluate_associations.py` compares confirmed records to fully adjudicated identities including explicit negative cases; it rejects demo rows for real accuracy evaluation.

Benchmark comparable image sizes, frame stride, model variants, CPU thread count, warmup, batch size and GPU builds. Dashboard pipeline FPS includes decode/tracking/database/evidence and excludes pauses; model-call FPS does not. Scripted demo FPS includes a deliberate UI-progress throttle and cannot be used as a YOLO benchmark.

## Non-negotiable limitations

Safety classification can be wrong with distance, occlusion, poor illumination, glare, rain, dirty lenses, low bitrate, tinted windscreens and unsuitable front/side/rear views. A top-down synthetic drawing is a software fixture, not evidence that seatbelts can be inferred from a real top-down camera. A high score is not a calibrated guilt probability. This system must not issue fines or other adverse decisions without independent, accountable human review and legally appropriate ground-truth validation.
