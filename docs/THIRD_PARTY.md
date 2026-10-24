# Licences, dependencies and provenance

## Project and sample

TrafficEye AI source is distributed under GNU AGPL-3.0 (`LICENSE`; SPDX AGPL-3.0-only). The original synthetic scene generator's scene artwork, rendered sample video and manifest are dedicated under CC0-1.0 (`samples/LICENSE-CC0.txt`). No real people, licence plates, CCTV clips or third-party traffic video are bundled.

Full licence texts were retrieved from the SPDX licence-list-data repository and verified to be non-empty licence texts during packaging:

- <https://github.com/spdx/license-list-data/blob/main/text/AGPL-3.0-only.txt>
- <https://github.com/spdx/license-list-data/blob/main/text/CC0-1.0.txt>

No custom-trained weights are supplied. The official COCO YOLO26 weights used only for delivery smoke verification are not redistributed in the project ZIP. The generic model prediction JSON is a test artifact, not a trained traffic-model claim.

## Dependencies

Dependencies retain their own licences and distribution obligations. Their installed packages provide authoritative texts. Key upstream projects:

| Component | Upstream / typical licence |
|---|---|
| Ultralytics YOLO26 and BoT-SORT implementation | <https://github.com/ultralytics/ultralytics> — AGPL-3.0 / enterprise licensing; review official terms |
| PyTorch / torchvision | <https://pytorch.org/> — BSD-style licences and bundled third-party notices |
| FastAPI / Starlette / Uvicorn / Pydantic | Respective upstream packages — MIT/BSD-style licences |
| OpenCV Python wheels | <https://github.com/opencv/opencv-python> — wheel contains OpenCV and third-party codec/library notices |
| NumPy / SciPy | BSD-style licences with bundled third-party components |
| React / Vite / Tailwind / Recharts | MIT licences in their upstream packages |
| Lucide | ISC licence / upstream icon notices |
| imageio-ffmpeg / FFmpeg encoder | imageio wrapper BSD; encoder build and libx264/FFmpeg licensing are separate and must be reviewed |
| SQLite | Public-domain core; Python's wrapper follows Python distribution notices |
| Playwright / pytest | Apache-2.0 / MIT-style test-tool licences, respectively |

The ZIP contains source, the original sample, a clean SQLite schema, docs/tests and a generated frontend build, not Python wheels, node_modules or native encoder/model binaries. Installation downloads dependencies from their official package indexes. Running the synthetic sample does not download third-party footage.

## Verified technical references

- YOLO26 usage and supported tasks: <https://docs.ultralytics.com/models/yolo26/>
- Object-detection validation: <https://docs.ultralytics.com/tasks/detect/>
- Tracking configuration: <https://docs.ultralytics.com/modes/track/>
- Python installation: <https://www.python.org/downloads/windows/>
- Matching PyTorch wheel selection: <https://pytorch.org/get-started/locally/>
- Node.js installers: <https://nodejs.org/>

Licensing and legal deployment requirements depend on your use. This document is a provenance/engineering notice, not legal advice or a substitute for reviewing actual upstream licence terms.
