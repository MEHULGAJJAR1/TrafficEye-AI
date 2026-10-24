"""Print actionable local diagnostics without exposing access keys or private results."""
import importlib
import importlib.metadata
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    print(f'Python {sys.version.split()[0]} | {platform.platform()} | executable: {sys.executable}')
    failed = []
    for module, package in [('fastapi','fastapi'),('uvicorn','uvicorn'),('cv2','opencv-python'),('numpy','numpy'),('torch','torch'),('torchvision','torchvision'),('ultralytics','ultralytics'),('lap','lap'),('imageio_ffmpeg','imageio-ffmpeg')]:
        try:
            imported = importlib.import_module(module)
            print(f'OK  {package}: {importlib.metadata.version(package)}')
            if module == 'torch':
                print(f'    CUDA available: {imported.cuda.is_available()}')
            if module == 'imageio_ffmpeg':
                print(f'    Encoder exists: {Path(imported.get_ffmpeg_exe()).exists()}')
        except Exception as exc:
            print(f'FAIL {package}: {type(exc).__name__}: {exc}')
            failed.append(package)
    if not failed:
        from backend.app.config import ConfigStore, Settings
        from backend.app.inference import ModelService
        settings = Settings(); settings.prepare()
        config = ConfigStore(settings.data_dir).get()
        print('Configured model:', ModelService(settings).status(config)['message'])
        print('Custom model missing is expected until your trusted weights are installed; demo works without them.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
