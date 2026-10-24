"""Verify the actual release ZIP, manifest, source syntax, clean database and sample checksum."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

EXPECTED = [
    'README.md', 'LICENSE', '.env.example', 'requirements.txt', 'requirements-dev.txt', 'pytest.ini',
    'backend/app/main.py', 'backend/app/api.py', 'backend/app/inference.py', 'backend/app/tracking.py',
    'backend/app/association.py', 'backend/app/processing.py', 'backend/app/database.py', 'backend/app/reporting.py',
    'backend/app/analytics.py', 'backend/app/security.py', 'backend/app/events.py', 'backend/app/config.py',
    'backend/tests/test_api.py', 'backend/tests/test_model.py',
    'frontend/package.json', 'frontend/package-lock.json', 'frontend/vite.config.js',
    'frontend/src/App.jsx', 'frontend/src/store.jsx', 'frontend/src/styles.css',
    'frontend/src/pages/Overview.jsx', 'frontend/src/pages/Workspace.jsx', 'frontend/src/pages/Settings.jsx',
    'frontend/tests/e2e/workflow.spec.js', 'frontend/dist/index.html',
    'scripts/Setup.ps1', 'scripts/Common.ps1', 'scripts/Start-All.ps1', 'scripts/Start-Backend.ps1',
    'scripts/Start-Frontend.ps1', 'scripts/Configure-Model.ps1', 'scripts/Prepare-Sample.ps1',
    'scripts/Test.ps1', 'scripts/Doctor.ps1', 'scripts/prepare_sample.py', 'scripts/init_workspace.py',
    'scripts/package_release.py', 'scripts/verify_release.py', 'scripts/smoke_release.py',
    'evaluation/evaluate_model.py', 'evaluation/evaluate_tracking.py', 'evaluation/evaluate_associations.py',
    'config/class_aliases.yaml', 'config/botsort.yaml', 'config/defaults.json',
    'data/trafficeye.sqlite3', 'samples/traffic_demo_60s.mp4', 'samples/demo_manifest.json',
    'samples/LICENSE-CC0.txt', 'models/README.md', 'docs/VERIFICATION.md', 'docs/dashboard.png',
    'docs/mobile.png', 'docs/API.md', 'docs/ARCHITECTURE.md', 'MANIFEST.sha256', 'RELEASE.json',
]


def verify(archive: Path):
    archive = archive.resolve()
    if not archive.is_file():
        raise FileNotFoundError(f'ZIP not found: {archive}')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    prefix = 'TrafficEye-AI/'
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP entries.')
        for name in names:
            path = PurePosixPath(name)
            if not name.startswith(prefix) or path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError(f'Unsafe ZIP entry: {name}')
            if '/node_modules/' in name or '/.venv/' in name or '/test-results/' in name or name.endswith('/access.key') or name.endswith('/.env') or name.lower().endswith('.pt'):
                raise ValueError(f'Secret/dependency/model weight accidentally packaged: {name}')
            if any(name.startswith(prefix + folder) for folder in ('data/uploads/', 'data/evidence/', 'data/frames/', 'data/previews/')):
                raise ValueError('Private runtime results were accidentally packaged.')
        missing = [p for p in EXPECTED if prefix + p not in names]
        if missing:
            raise ValueError('Missing required files: ' + ', '.join(missing))
        bad = z.testzip()
        if bad:
            raise ValueError(f'CRC failure: {bad}')
        manifest = z.read(prefix + 'MANIFEST.sha256').decode('utf-8').splitlines()
        verified = set()
        for line in manifest:
            expected, name = line.split('  ', 1)
            actual = hashlib.sha256(z.read(prefix + name)).hexdigest()
            if actual != expected:
                raise ValueError(f'Hash mismatch: {name}')
            verified.add(prefix + name)
        if set(names) - {prefix + 'MANIFEST.sha256'} != verified:
            raise ValueError('Manifest does not cover every bundled file.')
        source_count = 0
        for name in names:
            if name.endswith('.py'):
                ast.parse(z.read(name).decode('utf-8'), filename=name)
                source_count += 1
        sample = json.loads(z.read(prefix + 'samples/demo_manifest.json'))
        sample_hash = hashlib.sha256(z.read(prefix + 'samples/traffic_demo_60s.mp4')).hexdigest()
        if sample_hash != sample['sha256'] or sample['kind'] != 'scripted-synthetic-demo-not-ai':
            raise ValueError('The bundled demo video/manifest do not match.')
        html = z.read(prefix + 'frontend/dist/index.html').decode('utf-8')
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html):
            if prefix + 'frontend/dist' + asset not in names:
                raise ValueError('Production HTML references a missing asset: ' + asset)
        with tempfile.TemporaryDirectory(prefix='trafficeye-db-check-') as temp:
            database = Path(temp) / 'release.sqlite3'
            database.write_bytes(z.read(prefix + 'data/trafficeye.sqlite3'))
            with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
                integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
                counts = {table: conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('jobs','tracks','frames','violations','events','crossings')}
                schema = conn.execute('SELECT version FROM schema_version').fetchone()[0]
            if integrity != 'ok' or any(counts.values()) or schema != 1:
                raise ValueError('The release database is not a clean valid schema.')
    return {'status': 'passed', 'archive': archive.name, 'sha256': digest, 'size_bytes': archive.stat().st_size, 'file_count': len(names), 'manifest_verified_files': len(verified), 'python_sources_parsed': source_count, 'database_integrity': integrity, 'database_schema': schema, 'empty_database_counts': counts, 'sample_duration_seconds': sample['duration'], 'sample_sha256': sample_hash, 'custom_trained_weights_included': False, 'private_keys_or_runtime_results_included': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.archive)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
