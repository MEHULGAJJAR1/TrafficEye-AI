# API reference

Base URL for direct local API calls: `http://localhost:8000/api`. Browser code uses `/api` through Vite, including WebSockets. Interactive schemas: `/api/docs`; raw OpenAPI: `/api/openapi.json`.

## Authentication

`POST /auth/login` with `{"key":"your-local-key"}` sets `te_session`, an HttpOnly SameSite=strict signed 12-hour cookie. `GET /auth/status` returns only authenticated state and setup-key location, never the key. `POST /auth/logout` clears this browser's cookie. CLI/private routes also accept `Authorization: Bearer <key>`.

`health`, login/status and documentation are public. Every other REST route below requires authentication. The WebSocket requires a valid session cookie and an accepted Origin. A missing/invalid key returns 401; excessive failed login attempts return 429. Mutating browser requests from an untrusted Origin return 403. No private directory is statically mounted.

## Endpoints

| Method | Path (under /api) | Behavior |
|---|---|---|
| GET | `/health` | Public liveness/service version |
| GET | `/auth/status` | Public session state |
| POST | `/auth/login` | Local-key login |
| POST | `/auth/logout` | Clear session cookie |
| GET | `/system` | Actual schema-read check, model state, storage, queue and sample state |
| GET / PUT | `/config` | Read/save complete validated future-job config |
| POST | `/model/validate` | Load trusted configured local weights; report actual names, mapping and missing classes |
| POST | `/uploads` | Multipart field `file`; MP4/AVI/MOV, streamed to disk |
| POST | `/samples/demo` | Copy the verified bundled fixture into a new uploaded job |
| GET | `/jobs?limit=50&offset=0` | Persistent job list (no filesystem paths exposed) |
| GET | `/jobs/{uuid}` | Status/progress/options/config/latest detection+track packet |
| POST | `/jobs/{uuid}/start` | Queue uploaded job; body below |
| POST | `/jobs/{uuid}/pause` | Pause an active running job after current frame |
| POST | `/jobs/{uuid}/resume` | Resume paused in-memory job |
| POST | `/jobs/{uuid}/cancel` | Cooperatively cancel queued/running/paused job; keep partial results |
| POST | `/jobs/{uuid}/retry` | Reset terminal job and rerun; optional new start options |
| DELETE | `/jobs/{uuid}` | Remove inactive job, all owned files and cascading records |
| GET | `/jobs/{uuid}/video` | Authenticated H.264 browser preview; HTTP Range supported |
| GET | `/jobs/{uuid}/frame` | Authenticated latest annotated JPEG |
| GET | `/jobs/{uuid}/results?limit=20&offset=0` | Paginated persisted per-frame results, newest first |
| GET | `/tracks` | Paginated tracked identities; shared filters below |
| GET | `/violations` | Paginated confirmed records with evidence URLs; shared filters |
| GET | `/analytics` | Actual aggregates, time series, distributions and denominator definitions |
| GET | `/events` | `job_id`, `level`, `limit`, `before` integer event ID for cursor pagination |
| GET | `/evidence/{uuid}?download=true` | DB-owned evidence UUID only; optional attachment download |
| GET | `/reports.csv?kind=violations` | Streaming UTF-8 CSV, kinds `violations` or `vehicles`; shared filters |
| WS | `/ws/jobs/{uuid}` | Latest-state job packets with optional text `ping`/`pong` |

`start` body:

```json
{"mode":"real","max_seconds":60,"recorded_at":"2026-10-23T10:00:00+05:30"}
```

- `mode`: `real` or `demo`. Demo is restricted to the verified sample's SHA-256; it cannot annotate unrelated videos.
- `max_seconds`: default 60, `null` for the full uploaded video. Effective target is capped by source duration. Environment duration limit is applied at upload.
- `recorded_at`: optional timezone-aware recording start. Without it, import time + video offset is used, with `timestamp_basis=import-relative`. It is not claimed as original camera capture time.
- Missing/incompatible real model returns 409 before queue admission. Invalid bodies/configuration return 422. Invalid state transitions/full queue return 409.
- `retry` accepts the same optional body, otherwise reuses saved options. Restart-time jobs do not resume mid-video; they retry from frame zero.

## Shared result/analytics/report filters

| Query | Values |
|---|---|
| `job_id` | Optional job UUID string |
| `vehicle_class` | `Bike`, `Car`, `Jeep`, `Van` |
| `violation_type` | `No-Helmet`, `No-Seatbelt` |
| `min_confidence` | 0–1; tracks use peak vehicle score, violations use mean safety evidence score, box events use per-box score |
| `date_from`, `date_to` | Timezone-aware ISO 8601; normalized to UTC; from ≤ to |
| `source` | `all`, `real`, `demo`; never silently merge sources without provenance |
| `limit`, `offset` | For lists only; upper bounds enforced |

Tracks' date scope includes presence-interval overlap. Violation type filters narrow matching records/track lists; analytics' vehicle denominator remains all otherwise scoped identities. Frame counts/FPS describe scoped jobs, not a class-specific inference benchmark. See response `denominators` for exact semantics.

## Representative job packet

The values below describe the schema only; they are not benchmark results:

```text
type: job_update
version: monotonically increasing in-memory notification version
job:
  id, filename, width, height, fps, total_frames, duration
  status: uploaded | queued | running | paused | completed | cancelled | failed | interrupted
  preview_status: preparing | ready | failed | pending
  mode: real | demo | null
  processed_frames, decoded_frames, target_frames, progress (0..1)
  video_time, elapsed, processing_fps, inference_fps, detection_events
  config, options, timestamp_basis, recorded_at, error
  last_result:
    frame_index, video_time, occurred_at, mode, width, height, inference_ms
    detections: [{class_name, confidence, bbox:[x1,y1,x2,y2], track_id|null}]
    tracks: [{track_id, class_name, bbox, confidence, zone, helmet_status, seatbelt_status}]
```

Raw safety boxes do not receive vehicle IDs. Their confirmed association is recorded in the violation's vehicle/object bounding boxes and track ID. Initial unconfirmed vehicle detections can have a null track ID; no ID is fabricated.

## PowerShell example: complete labelled demo

```powershell
$Base = 'http://localhost:8000/api'
$Key = (Get-Content .\data\access.key -Raw).Trim()
$Headers = @{ Authorization = "Bearer $Key" }
$Job = Invoke-RestMethod "$Base/samples/demo" -Method Post -Headers $Headers
$Options = @{ mode = 'demo'; max_seconds = 60 } | ConvertTo-Json
Invoke-RestMethod "$Base/jobs/$($Job.id)/start" -Method Post -Headers $Headers -ContentType 'application/json' -Body $Options
Invoke-RestMethod "$Base/jobs/$($Job.id)" -Headers $Headers
# After status is completed:
Invoke-WebRequest "$Base/reports.csv?job_id=$($Job.id)&kind=violations" -Headers $Headers -OutFile .\demo-violations.csv
```

This mode produces **scripted synthetic** results. For real data, upload a legal source and use the validated custom model with mode real. Never use demo records as accuracy evidence.

## Errors and media safety

400 invalid path/origin-independent bad input; 401 unauthorized; 403 untrusted browser mutation Origin; 404 absent job/media; 409 state/model/queue/preview conflict; 413 oversized request/file; 415 unsupported extension; 422 malformed body/unreadable video/invalid filters; 429 login throttling; 500 unexpected failure with backend-log guidance. User-controlled filenames are never interpolated into shell commands, SQL or media paths.
