"""Export processed vehicle boxes from a stopped/local SQLite database for labelled tracking comparison."""
import argparse
import csv
import json
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error('Database not found.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db, args.output.open('w', newline='', encoding='utf-8') as file:
        job = db.execute('SELECT mode FROM jobs WHERE id=?', (args.job_id,)).fetchone()
        if not job:
            parser.error('Job ID not found.')
        writer = csv.writer(file)
        writer.writerow(['frame', 'vehicle_id', 'vehicle_class', 'x1', 'y1', 'x2', 'y2'])
        for index, payload in db.execute('SELECT frame_index,payload FROM frames WHERE job_id=? ORDER BY frame_index', (args.job_id,)):
            for track in json.loads(payload)['tracks']:
                writer.writerow([index, track['track_id'], track['class_name'], *track['bbox']])
    print(f'Exported {job[0]}-mode tracks to {args.output}. Match frame sampling and image dimensions in your ground truth.')
    if job[0] == 'demo':
        print('WARNING: these are synthetic fixture tracks, not valid real-world performance data.')


if __name__ == '__main__':
    main()
