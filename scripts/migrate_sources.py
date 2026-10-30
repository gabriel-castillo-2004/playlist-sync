#!/usr/bin/env python3
"""Script for exporting and importing Playlist Sync sources via JSON across machines.

Usage:
    python scripts/migrate_sources.py export [sources.json]
    python scripts/migrate_sources.py import [sources.json]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src directory to path if run standalone
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from playlist_sync.adapters.composite_source import CompositeSource  # noqa: E402
from playlist_sync.adapters.repo import SQLiteRepo  # noqa: E402
from playlist_sync.main import load_config  # noqa: E402
from playlist_sync.services.migration import export_sources_to_json, import_sources_from_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Playlist Sync database sources between machines using JSON."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    export_parser = subparsers.add_parser("export", help="Export sources to JSON file")
    export_parser.add_argument(
        "file",
        nargs="?",
        default="sources.json",
        help="Target JSON file path (default: sources.json)",
    )

    import_parser = subparsers.add_parser("import", help="Import sources from JSON file")
    import_parser.add_argument(
        "file",
        nargs="?",
        default="sources.json",
        help="Source JSON file path (default: sources.json)",
    )

    args = parser.parse_args()
    cfg = load_config()
    storage_cfg = cfg.get("storage") if isinstance(cfg.get("storage"), dict) else {}
    db_path = str(storage_cfg.get("database_path", "playlist_sync.sqlite3"))

    repo = SQLiteRepo(db_path)

    if args.action == "export":
        out_path = export_sources_to_json(repo, args.file)
        print(f"[OK] Fuentes exportadas exitosamente a: {out_path}")
        return 0

    if args.action == "import":
        source_adapter = CompositeSource()
        results = import_sources_from_json(repo, source_adapter, args.file)
        print(
            f"[OK] Importación finalizada: {results['imported']} importadas, {results['skipped']} omitidas."
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
