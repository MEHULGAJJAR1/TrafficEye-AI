"""Create the included original CC0 fixture offline; never downloads unverified traffic footage."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.demo import DEMO_NAME, MANIFEST_NAME, prepare_sample, sha256

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Regenerate the deterministic synthetic sample.")
    args = parser.parse_args()
    import json
    source = ROOT / "samples" / DEMO_NAME
    manifest = ROOT / "samples" / MANIFEST_NAME
    if source.exists() and manifest.exists() and not args.force and sha256(source) == json.loads(manifest.read_text()).get("sha256"):
        print(f"Verified existing 60-second synthetic sample: {source}")
    else:
        print("Rendering original synthetic fixture (720 frames); these are not camera images or AI predictions...")
        print(prepare_sample(ROOT / "samples"))
