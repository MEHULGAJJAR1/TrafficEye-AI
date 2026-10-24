"""Copy explicitly supplied trusted weights into models/ and validate their label schema."""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import ConfigStore, RuntimeConfig, Settings
from backend.app.inference import ModelService, ModelUnavailable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', type=Path, help='Trusted .pt file to copy; omitted means inspect the saved filename.')
    parser.add_argument('--name', default='traffic-custom.pt', help='Destination filename within models/.')
    args = parser.parse_args()
    settings = Settings()
    settings.prepare()
    store = ConfigStore(settings.data_dir)
    config = store.get()
    if args.weights:
        if not args.weights.is_file() or args.weights.suffix.lower() != '.pt':
            parser.error('--weights must be an existing trusted .pt file.')
        try:
            RuntimeConfig.model_validate({**config.model_dump(), 'model_file': args.name})
        except ValueError:
            parser.error('--name must be a simple local .pt filename, such as traffic-custom.pt, without directory separators.')
        destination = settings.model_dir / args.name
        if args.weights.resolve() != destination.resolve():
            if destination.exists() or destination.is_symlink():
                parser.error(f'{destination} already exists. Back it up/remove it or choose another --name; existing weights are never overwritten silently.')
            shutil.copy2(args.weights, destination)
        config.model_file = args.name
        # Validate the candidate first; rejected weights must not break the saved selection.
    service = ModelService(settings)
    try:
        service.load(config)
    except ModelUnavailable as exc:
        print(f'MODEL NOT READY: {exc}')
        print('The labelled synthetic demo remains available.')
        return 2
    if args.weights:
        store.save(config)
    print(json.dumps(service.status(config), indent=2))
    print('Class-schema validation passed. This does NOT certify model accuracy.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
