"""Compare local model/runtime files with recorded SHA-256 values. No inference is run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=['model', 'llama_mtp', 'strata', 'binaries', 'all'], default='model')
    parser.add_argument('--paths', default='configs/paths.local.json')
    args = parser.parse_args()
    paths = load(ROOT / 'configs/paths.example.json')
    override = ROOT / args.paths
    if override.exists():
        paths.update(load(override))
    assets = load(ROOT / 'docs/assets.json')['assets']
    failed = 0
    for asset in assets:
        if args.group != 'all' and args.group != asset['group']:
            continue
        if asset.get('path_key'):
            candidate = ROOT / paths[asset['path_key']]
            if asset.get('relative_to_key'):
                if asset.get('relative_to_key_parent'):
                    candidate = candidate.parent
                candidate = candidate / asset['relative_to_key']
        else:
            candidate = ROOT / asset['path']
        if not candidate.is_file():
            print(f'MISSING {asset["path"]}', flush=True)
            failed += 1
            continue
        if candidate.stat().st_size != asset['bytes']:
            print(f'SIZE MISMATCH {asset["path"]}', flush=True)
            failed += 1
            continue
        digest = hashlib.sha256()
        with candidate.open('rb') as handle:
            for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b''):
                digest.update(chunk)
        matches = digest.hexdigest() == asset['sha256']
        print(f'{"OK" if matches else "SHA256 MISMATCH"} {asset["path"]}', flush=True)
        if not matches:
            print('  actual: ' + digest.hexdigest(), flush=True)
            failed += 1
    return int(bool(failed))


if __name__ == '__main__':
    sys.exit(main())
