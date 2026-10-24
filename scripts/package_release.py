"""Build a clean source+compiled-frontend ZIP, never a snapshot of private runtime data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.database import Database
from scripts.verify_release import verify

SKIP_DIRS = {'.git','.venv','node_modules','__pycache__','.pytest_cache','.cache','.npm','.vite','.ruff_cache','test-results','playwright-report','dist','release','data','models','build','coverage'}
SKIP_FILES = {'.env','.coverage','access.key','.DS_Store'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'TrafficEye-AI.zip')
    args = parser.parse_args()
    if not (ROOT / 'frontend/dist/index.html').exists():
        parser.error('Build the frontend first: cd frontend; npm ci; npm run build')
    if not (ROOT / 'docs/VERIFICATION.md').exists():
        parser.error('Record actual verification results before packaging.')
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trafficeye-release-') as temp:
        stage = Path(temp) / 'TrafficEye-AI'
        stage.mkdir()
        for directory, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for filename in files:
                path = Path(directory) / filename
                if filename in SKIP_FILES or filename.endswith(('.pyc','.pt','.zip','.sqlite3-wal','.sqlite3-shm')):
                    continue
                dest = stage / path.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
        shutil.copytree(ROOT / 'frontend/dist', stage / 'frontend/dist')
        (stage / 'models').mkdir()
        shutil.copy2(ROOT / 'models/README.md', stage / 'models/README.md')
        (stage / 'data').mkdir()
        shutil.copy2(ROOT / 'data/README.md', stage / 'data/README.md')
        db = Database(stage / 'data/trafficeye.sqlite3')
        with db.connect() as connection:
            connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        for suffix in ('-wal','-shm'):
            Path(str(db.path) + suffix).unlink(missing_ok=True)
        release = {'project': 'TrafficEye AI', 'version': '1.0.0', 'built_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'database': 'clean schema only', 'sample': 'original 60-second CC0 synthetic video; demo observations are scripted, not AI', 'required_for_real_safety_inference': 'trusted, adequately trained YOLO26 .pt weights with all eight required classes; not supplied', 'evaluation_requires': 'suitable independently labelled real traffic validation/ground-truth data', 'default_runtime': 'single-process local workstation, SQLite, CPU PyTorch; optional supported CUDA hardware', 'no_secrets_or_custom_weights_bundled': True}
        (stage / 'RELEASE.json').write_text(json.dumps(release, indent=2)+'\n',encoding='utf-8')
        entries = sorted(p for p in stage.rglob('*') if p.is_file())
        private_values = []
        source_key = ROOT / 'data/access.key'
        if source_key.is_file():
            private_values.append(source_key.read_bytes().strip())
        if os.environ.get('TE_API_KEY'):
            private_values.append(os.environ['TE_API_KEY'].encode())
        private_values = [value for value in private_values if len(value) >= 24]
        for path in entries:
            if any(value in path.read_bytes() for value in private_values):
                raise RuntimeError('A private access key was found in a staged file: ' + path.relative_to(stage).as_posix())
        manifest = '\n'.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(stage).as_posix()}' for p in entries) + '\n'
        (stage / 'MANIFEST.sha256').write_text(manifest,encoding='utf-8')
        with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(p for p in stage.rglob('*') if p.is_file()):
                archive.write(path, path.relative_to(stage.parent).as_posix())
    result = verify(args.output)
    args.output.with_suffix('.zip.sha256').write_text(f"{result['sha256']}  {args.output.name}\n",encoding='utf-8')
    report = args.output.with_name('TrafficEye-AI-release-verification.json')
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    print('Verified actual ZIP:', args.output)
    print('External verification:', report)


if __name__ == '__main__':
    main()
