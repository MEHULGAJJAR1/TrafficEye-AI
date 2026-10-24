# Verification record — TrafficEye AI 1.0.0

Verified on **23 October 2026**. This records actual execution, not an assertion that untested hardware, training quality or deployments are ready.

## Scope and environment

- Linux x86-64; Python **3.13.16**, Node **20.20.2**, npm **10.8.2**.
- CPU only: PyTorch **2.9.1+cpu**, torchvision **0.24.1+cpu**, Ultralytics **8.4.184** with the installed YOLO26 architecture.
- FastAPI **0.161.1**, Starlette **1.9.0**, OpenCV **4.11.0.86**, NumPy **2.3.5**.
- React **19.3.1**, Recharts **3.10.1**, Vite **6.4.5**, Tailwind / Tailwind PostCSS **4.3.3**, Playwright **1.64.1**.
- Full measured versions: `environment.json`. No CUDA device was available.

No custom-trained eight-class safety checkpoint, real annotated traffic validation set, tracking ground truth or human association ground truth was supplied. **No real helmet/seatbelt accuracy or enforcement suitability is claimed.**

## Final executed checks

| Check | Actual result | Evidence |
|---|---|---|
| Backend unit + API + inference/evaluation protocol suite | **73 passed**, **88% backend statement coverage**, **34.92 s**, no skipped tests in this run | `backend-test-output.txt`, `backend-tests.xml`, `backend-coverage.xml` |
| Frontend utility tests | **10 passed**, 0 failed | `frontend-test-output.txt` |
| Fresh frontend lockfile installation | `npm ci --no-fund --no-audit` completed | `frontend-install-output.txt` |
| Production frontend build | **Passed**, 2,179 modules, 9.50 s | `frontend-build-output.txt` |
| Chromium against the production Vite preview | **3 passed**, **36.8 s**, 1 worker | `browser-test-output.txt`, `browser-tests.json` |
| Production + complete npm dependency audits | **0 vulnerabilities** in both final audits | `npm-audit-production.json`, `npm-audit-all.json` |
| Python dependency compatibility | `pip check`: **No broken requirements found** | `python-dependency-check.txt` |
| Import/bootstrap helper + diagnostic helper | Both completed; missing custom model reported explicitly | `import-check.txt`, `doctor-output.txt` |
| Windows PowerShell script syntax | **9 scripts parsed** using real Linux PowerShell 7.6.8 | `powershell-syntax.txt` |
| Setup native argument handling | Helper and all 3 literal Python/Node validation commands executed; also tested Legacy argument passing | `powershell-syntax.txt` |
| Release archive integrity / extracted release smoke | Run by the release helpers **after packaging**; the accompanying external JSON reports contain the actual ZIP SHA-256 and authoritative results | `TrafficEye-AI-release-verification.json` / `TrafficEye-AI-release-smoke.json` delivered beside the ZIP |

The backend suite emits **one Starlette TestClient deprecation warning** for its working, pinned `httpx` adapter. It is not a failed test. Python `pip check` is dependency-compatibility checking, **not a Python vulnerability audit**. npm audit is a point-in-time advisory check, not proof of security.

## What the backend tests actually exercise

- Authenticated and unauthenticated routes/media, signed sessions, wrong-key throttling, Origin checks and unauthenticated WebSocket rejection.
- MP4, AVI and MOV metadata/decoder checks; empty, corrupt, unsafe-name, unsupported and oversized/chunked requests; malformed/non-finite JSON returns safe 422 errors without reflecting raw secret input.
- Synthetic sample checksum gating; arbitrary footage cannot invoke scripted demo detections. A corrupt manifest disables the sample without crashing the application.
- Default/full-video modes, explicit stride (720 decoded source frames / 72 analyzed samples at stride 10), pause, resume, cancellation, queue limits, retry and per-job immutable configuration.
- Genuine BoT-SORT API execution with stable IDs across controlled box fixtures, separate from the explicit demo tracker.
- Spatial association, confidence/size gates, unknown/conflicting/ambiguous evidence, zones, finite-line crossings, one count per direction, duplicate suppression and rule-confirmed JPEG generation.
- Voting at **12, 25, 30, 60, 120 and 240 FPS**, with no early confirmation before minimum video-time maturity and a reset when window support is lost. Maturity carries across consecutive qualifying rolling windows; limiting .25 s to seven frames would otherwise make normal 25+ FPS footage impossible to confirm. This issue was fixed and regression-tested.
- SQLite checkpoints/restart persistence, interrupted-job recovery, orphan-file cleanup, analytics denominator/filter semantics, safe CSV serialization and evidence access.
- The configure-model CLI accepts an explicitly untrained schema fixture, refuses overwrite/path names, rejects invalid weights, and preserves saved working selection on failure. The track-export CLI reads actual checkpointed fixture boxes and warns about synthetic provenance.

### Actual model execution, without manufactured accuracy

Tests initialize a **random, untrained YOLO26 nano network** with eight labels from the installed architecture. They run real CPU prediction; a real-mode 12-frame OpenCV → PyTorch → BoT-SORT → SQLite → CSV workflow; and actual Ultralytics validation on original synthetic labels, including a 9×9 confusion matrix, eight per-class entries and PNG/JSON output. These prove executable plumbing and serialization **only**, not traffic accuracy. Random checkpoints are not bundled as trained weights.

A separately downloaded official generic `yolo26n.pt` was run on Ultralytics' published bus example and returned four person objects and one bus; the measured report is `generic-model-smoke.json`. This is only a generic installation/inference probe. That model is explicitly rejected by the traffic class-schema check. Neither the generic weights nor the third-party image are included in the ZIP.

The full run set `TE_TEST_COCO_WEIGHTS` to that verified local official checkpoint. A normal installation without this optional fixture will skip that one generic-model compatibility test rather than downloading a model silently.

## Actual browser workflow

The final browser tests were run against **the compiled production build**, proxied to the freshly restarted backend:

1. Unlock → choose local MP4 → inspect local preview → actual HTTP upload (201).
2. Start scripted sample analysis → nonzero progress → Pause → Resume → live frame inspector and authenticated WebSocket.
3. Cancel → Reprocess → complete **all 720 frames**.
4. Inspect actual saved evidence, open JPEG detail/download, download CSV, assert demo provenance and required fields, and filter tracked vehicles.
5. Visit all ten views; exercise configuration validation/save, unsupported-file errors, 390-pixel mobile navigation/no horizontal page overflow, session locking and a forced WebSocket outage with genuine HTTP polling updates.
6. Fail on browser page errors; none were observed. Remove only the jobs created by the test run.

`dashboard.png` and `mobile.png` are **actual screenshots**, visually inspected after the final build; no dashboard screenshot was generated by an image model. They display the labelled synthetic workflow. Transient notifications are dismissed and chart reflow is allowed to settle before capture.

### Observed synthetic fixture output

From `demo-workflow-result.json`, final full-length browser job `d7476017-e31f-48b5-8848-e96505ca1d5a`:

| Quantity | Observed value |
|---|---:|
| Source duration / FPS / analyzed frames | 60 s / 12 / 720 |
| Unique tracker identities | 28 (7 each Bike, Car, Jeep, Van) |
| Confirmed scripted rule records | 11 (4 No-Helmet + 7 No-Seatbelt) |
| Scoped unique violating identities | 11 |
| Displayed rate denominator | 11 / 28 = 39.29% |
| Class-labelled box observations (including safety boxes) | 4,249 |
| IN / OUT events | 13 / 14 |
| Active processing elapsed | 22.873 s |
| Measured whole scripted pipeline rate | 31.48 sampled frames/s |
| Model inference rate | 0 — no model ran in demo |

These are deliberately throttled **synthetic software-fixture observations**, not an ML accuracy table or transferable hardware/performance benchmark. One physical vehicle can fragment into multiple tracker identities in real footage. Percentages use scoped unique identities, not repeated detection boxes.

## Release acceptance and reproducibility

The release packager explicitly starts from source and a **new empty initialized SQLite schema**. It does not copy the private development `data/` directory. It includes the compiled frontend, package lock, Python requirements, tests, model/configuration instructions, nine Windows launch/setup/test scripts, original 60-second CC0 sample and full licence texts. No custom weights, API key, `.env`, node_modules, virtual environment, upload, evidence or live result database is intentionally bundled. Known working access-key values are scanned out of staged files.

`package_release.py` creates the actual ZIP, per-file SHA-256 manifest and an adjacent archive checksum. `verify_release.py` then checks CRCs, required entries, traversal/dependency/secret-path exclusions, manifest coverage for every file, Python source syntax, production asset references, sample hash, database schema/integrity and zero runtime rows.

`smoke_release.py --rebuild-frontend` extracts that **actual archive** into a temporary directory, installs/builds its frontend from its lockfile, imports its own backend source, creates a fresh random key, checks empty state and missing-model messaging, uploads/processes a 3-second/36-frame part of the bundled MP4, decodes saved evidence, checks vehicle/violation CSVs and UTC conversion, then restarts the application and checks SQLite/media persistence. Its external JSON is tied to the final ZIP hash. It uses already installed Python requirements; it does not pretend to be a new isolated Python installation.

See README section 7 for exact Windows verification/rebuild commands. Archive hashes are external to avoid self-reference; the supplied JSON reports are authoritative for the delivered file's final byte count, file count and SHA-256.

## Untested acceptance boundaries and exact next steps

| Not established here | What is required next |
|---|---|
| Windows runtime setup/start, PowerShell 5.1 behavior, Windows wheel/codec availability | On a supported 64-bit Windows workstation, install Python 3.11–3.13 and Node 22/24 LTS, run `scripts\Setup.ps1`, `Start-All.ps1`, then `Test.ps1 -Browser`. Linux parsing/Legacy-argument checks do not replace this. |
| Fresh isolated Python requirements installation | Run the supplied Setup in a new workspace/venv; preserve its pip log. Existing Linux environment imports/tests and `pip check` passed. |
| Real custom traffic inference quality | Supply trusted, trained YOLO26 detection weights with all eight required class names, run Configure-Model/Settings validation, upload legally obtained real footage, inspect raw boxes and manually review evidence. |
| Precision/recall/mAP for real safety detection | Supply a properly split independently labelled real dataset and run `evaluation/evaluate_model.py`; inspect per-class metrics and confusion matrix. No scores have been invented. |
| Real tracker/driver/rider association accuracy | Annotate identities/boxes and adjudicated positive **and negative** decisions. Use the supplied tracking/association tools as documented; they are diagnostics, not official HOTA/IDF1 or a physical-identity guarantee. |
| CUDA/MPS execution, OOM handling on hardware, GPU throughput | Install a matching supported CUDA wheel/driver pair, select/validate device, process your footage and measure actual job/evaluation timing. CPU fallback exists; GPU execution was unavailable here. |
| Every browser, variable-frame-rate timing, RTSP/live cameras, long-haul deployment | Validate your target browser/codec/camera. Re-encode VFR to CFR for this version. RTSP and live capture are not implemented or advertised. |
| Hardened multi-tenant/internet deployment or legal enforcement | Obtain a security/privacy/legal review, TLS/proxy controls, native-code isolation, access/retention policy and camera-specific audited validation. This is a local single-operator application; do not issue automatic penalties. |
| PDF reporting | Deliberately not implemented. CSV and individual JPEG downloads are the tested formats. |

Pause/cancel act at frame boundaries; **preview transcoding is a separate bounded worker and its external encoder is not cooperatively cancelable**. It can delay shutdown until it completes or times out. Reprocessing starts from zero. Sessions are stateless signed cookies, not individually revocable tokens. These are documented design limits, not hidden features.
