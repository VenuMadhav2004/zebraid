"""Repeatable CLI importer for the Zebra 3D Models dataset (Google Drive or local folder).

Usage:
  python scripts/import_zebra_3d_dataset.py --target D:/zebid/data/zebra_3d_scans
  python scripts/import_zebra_3d_dataset.py --discover-only
  python scripts/import_zebra_3d_dataset.py --source /path/to/local/scans --target D:/zebid/data/zebra_3d_scans
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.services.hide_scan_importer import (  # noqa: E402
    DEFAULT_DRIVE_FOLDER_ID,
    discover_google_drive_tree,
    import_from_google_drive,
    import_from_local_directory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and register Zebra 3D Models into HIDE_SCANS_DIR.")
    parser.add_argument("--drive-folder", default=DEFAULT_DRIVE_FOLDER_ID, help="Public Google Drive folder ID")
    parser.add_argument("--source", type=Path, default=None, help="Optional local dataset directory instead of Google Drive")
    parser.add_argument("--target", type=Path, default=None, help="Destination HIDE_SCANS_DIR (defaults to .env HIDE_SCANS_DIR)")
    parser.add_argument("--discover-only", action="store_true", help="List Google Drive files without downloading")
    args = parser.parse_args()

    if args.discover_only:
        nodes = discover_google_drive_tree(args.drive_folder)
        files = [n for n in nodes if not n.is_folder]
        print(f"Discovered {len(files)} files across {len(nodes) - len(files)} directories.")
        for n in files[:50]:
            print(f"  {n.rel_path} ({n.file_id})")
        if len(files) > 50:
            print(f"  ... ({len(files) - 50} more)")
        return 0

    target = args.target or (Path(get_settings().hide_scans_dir) if get_settings().hide_scans_dir else None)
    if target is None:
        print("Error: --target is required when HIDE_SCANS_DIR is not set.", file=sys.stderr)
        return 2

    if args.source is not None:
        summary = import_from_local_directory(args.source, target)
    else:
        summary = import_from_google_drive(args.drive_folder, target)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
