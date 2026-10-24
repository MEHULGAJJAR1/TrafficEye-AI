"""Initialize SQLite and a private access key; safe to run repeatedly."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import ConfigStore, Settings
from backend.app.database import Database
from backend.app.security import Auth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-imports', action='store_true')
    args = parser.parse_args()
    if args.check_imports:
        import cv2, fastapi, imageio_ffmpeg, lap, numpy, torch, torchvision, ultralytics, uvicorn
        print(f'Imports OK | Python {sys.version.split()[0]} | PyTorch {torch.__version__} | CUDA available: {torch.cuda.is_available()}')
    settings = Settings()
    settings.prepare()
    Database(settings.data_dir / 'trafficeye.sqlite3')
    ConfigStore(settings.data_dir)
    Auth(settings)
    print('Workspace initialized. No custom model weights are included.')
    print(f'Database: {settings.data_dir / "trafficeye.sqlite3"}')
    print('Unlock using your TE_API_KEY environment value.' if settings.api_key else f'Access key file: {settings.data_dir / "access.key"}')


if __name__ == '__main__':
    main()
