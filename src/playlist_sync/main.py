"""CLI entrypoint for Playlist Sync (Phase 1)."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

from playlist_sync.adapters.composite_source import CompositeSource
from playlist_sync.adapters.repo import SQLiteRepo
from playlist_sync.core.errors import AppError
from playlist_sync.core.models import Progress, Source
from playlist_sync.doctor import run_doctor
from playlist_sync.services.backup import create_database_backup, restore_database_backup
from playlist_sync.services.migration import export_sources_to_json, import_sources_from_json
from playlist_sync.services.sync import add_source_service, sync_source_service


def load_config() -> dict[str, object]:
    """Load config.toml if present, otherwise return defaults."""
    cfg_path = Path("config.toml")
    if cfg_path.exists():
        try:
            with cfg_path.open("rb") as f:
                return tomllib.load(f)
        except Exception:
            pass
    return {
        "storage": {
            "database_path": "playlist_sync.sqlite3",
            "music_root": "music_root",
            "min_disk_free_mb": 1024,
        },
        "sync": {
            "safety_threshold": 0.50,
            "max_retries": 3,
        },
    }


def cli_progress_hook(progress: Progress) -> None:
    """Print clean download progress to stderr or stdout."""
    title = (progress.current_item_title or "")[:30]
    speed_kb = (progress.speed_bytes_per_sec / 1024) if progress.speed_bytes_per_sec else 0
    percent_str = f"{progress.percentage:.1f}%"
    print(
        f"\rDescargando: {title:<30} | {percent_str:>6} ({speed_kb:.0f} KB/s)",
        end="",
        flush=True,
    )


def cmd_add(url: str, repo: SQLiteRepo, source_adapter: Source) -> int:
    """Handle 'add <url>' command."""
    print(f"Inspeccionando enlace: {url}...")
    try:
        source = add_source_service(repo, source_adapter, url)
        print("\n[OK] Fuente registrada exitosamente:")
        print(f"    ID:     {source.id}")
        print(f"    Titulo: {source.title}")
        print(f"    Carpeta: {source.folder_name}")
        return 0
    except AppError as err:
        print(f"\n[ERROR] {err.user_message}")
        if err.technical_detail:
            print(f"    Detalle: {err.technical_detail}")
        return 1


def cmd_sync(
    source_target: str,
    repo: SQLiteRepo,
    source_adapter: Source,
    music_root: Path,
    safety_threshold: float,
    max_retries: int,
    min_disk_free_mb: int,
) -> int:
    """Handle 'sync <id|all>' command."""
    if source_target.lower() == "all":
        sources = repo.list_sources()
        if not sources:
            print("No hay fuentes registradas para sincronizar.")
            return 0
    else:
        try:
            source_id = int(source_target)
        except ValueError:
            print(f"Error: '{source_target}' no es un ID valido (debe ser un numero o 'all').")
            return 1
        source = repo.get_source(source_id)
        if not source:
            print(f"Error: No existe ninguna fuente con el ID {source_id}.")
            return 1
        sources = [source]

    total_downloaded = 0
    total_failed = 0

    for src in sources:
        print(f"\nSincronizando fuente #{src.id}: '{src.title}'...")
        try:
            res = sync_source_service(
                repo=repo,
                source_adapter=source_adapter,
                source_id=src.id,
                music_root=music_root,
                on_progress=cli_progress_hook,
                min_free_mb=min_disk_free_mb,
                safety_threshold=safety_threshold,
                max_retries=max_retries,
            )
            print()  # Newline after progress hook
            print(f"[OK] Sincronizacion finalizada para '{src.title}':")
            print(f"    Descargadas: {res.downloaded_count}")
            print(f"    Al dia:      {res.skipped_count}")
            print(f"    Falladas:    {res.failed_count}")
            if res.removed_count > 0:
                print(
                    f"    Retiradas de la playlist remota: {res.removed_count} (archivos conservados)"
                )
            if res.failed_items:
                print("    Errores:")
                for ext_id, msg in res.failed_items:
                    print(f"      - [{ext_id}]: {msg}")

            total_downloaded += res.downloaded_count
            total_failed += res.failed_count
        except AppError as err:
            print()
            print(f"[ERROR] {err.user_message}")
            if err.technical_detail:
                print(f"    Detalle: {err.technical_detail}")
            total_failed += 1

    return 0 if total_failed == 0 else 1


def cmd_status(repo: SQLiteRepo) -> int:
    """Handle 'status' command."""
    sources = repo.list_sources()
    if not sources:
        print("No hay fuentes registradas.")
        print("Usa 'python -m playlist_sync add <url>' para agregar una playlist de YouTube.")
        return 0

    print("=" * 70)
    print("Playlist Sync — Estado de las Fuentes")
    print("=" * 70)
    for src in sources:
        items = repo.get_items_by_source(src.id)
        downloaded = sum(1 for it in items if it.status.value == "downloaded")
        pending = sum(1 for it in items if it.status.value == "pending")
        errors = sum(1 for it in items if it.status.value == "error")

        sync_str = src.last_sync_at.strftime("%Y-%m-%d %H:%M") if src.last_sync_at else "Nunca"
        print(f"[{src.id}] {src.title}")
        print(f"    Estado:       {src.status.value.upper()}")
        print(
            f"    Elementos:    {downloaded} descargados | {pending} pendientes | {errors} errores"
        )
        print(f"    Ultima sinc.: {sync_str}")
        if src.last_error_message:
            print(f"    Ultimo error: {src.last_error_message}")
        print("-" * 70)
    return 0


def cmd_export(repo: SQLiteRepo, file_path: str = "sources.json") -> int:
    """Export tracked sources to JSON file."""
    try:
        out = export_sources_to_json(repo, file_path)
        print(f"[OK] Fuentes exportadas exitosamente a: {out}")
        return 0
    except Exception as exc:
        print(f"[ERROR] No se pudo exportar: {exc}")
        return 1


def cmd_import(repo: SQLiteRepo, source_adapter: Source, file_path: str = "sources.json") -> int:
    """Import sources from JSON file."""
    try:
        res = import_sources_from_json(repo, source_adapter, file_path)
        print(f"[OK] Importacion exitosa: {res['imported']} importadas, {res['skipped']} omitidas.")
        return 0
    except Exception as exc:
        print(f"[ERROR] No se pudo importar: {exc}")
        return 1


def cmd_backup(db_path: str, backup_dir: str = "backups") -> int:
    """Create a consistent database backup."""
    try:
        out = create_database_backup(db_path, backup_dir)
        print(f"[OK] Respaldo de base de datos generado en: {out}")
        return 0
    except Exception as exc:
        print(f"[ERROR] No se pudo crear respaldo: {exc}")
        return 1


def cmd_restore_backup(backup_file: str, db_path: str) -> int:
    """Restore the SQLite database from a backup file."""
    try:
        out = restore_database_backup(backup_file, db_path)
        print(f"[OK] Base de datos restaurada exitosamente en: {out}")
        return 0
    except Exception as exc:
        print(f"[ERROR] No se pudo restaurar el respaldo: {exc}")
        return 1


def main() -> None:
    """CLI router for Playlist Sync."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="playlist-sync",
        description="Playlist Sync: Descarga playlists de YouTube y podcasts como MP3 locales.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Comandos disponibles")

    # Doctor
    subparsers.add_parser("doctor", help="Verificar salud y requisitos del sistema")

    # Add
    parser_add = subparsers.add_parser("add", help="Registrar una nueva playlist")
    parser_add.add_argument("url", help="URL de la playlist publica de YouTube o YouTube Music")

    # Sync
    parser_sync = subparsers.add_parser("sync", help="Sincronizar una fuente o todas")
    parser_sync.add_argument(
        "target", help="ID de la fuente (ej. '1') o 'all' para sincronizar todas"
    )

    # Status
    subparsers.add_parser("status", help="Consultar estado de las fuentes registradas")

    # Export
    parser_export = subparsers.add_parser("export", help="Exportar fuentes a un archivo JSON")
    parser_export.add_argument(
        "file", nargs="?", default="sources.json", help="Ruta del archivo JSON"
    )

    # Import
    parser_import = subparsers.add_parser("import", help="Importar fuentes desde un archivo JSON")
    parser_import.add_argument(
        "file", nargs="?", default="sources.json", help="Ruta del archivo JSON"
    )

    # Backup
    parser_backup = subparsers.add_parser(
        "backup", help="Crear un respaldo seguro de la base de datos"
    )
    parser_backup.add_argument("--dir", default="backups", help="Directorio destino del respaldo")

    # Restore backup
    parser_restore = subparsers.add_parser(
        "restore-backup", help="Restaurar la base de datos desde un archivo de respaldo"
    )
    parser_restore.add_argument("backup_file", help="Ruta del archivo de respaldo .sqlite3")

    # Serve
    parser_serve = subparsers.add_parser("serve", help="Iniciar servidor web local (FastAPI)")
    parser_serve.add_argument("--host", default=None, help="Dirección host a enlazar")
    parser_serve.add_argument("--port", type=int, default=None, help="Puerto a enlazar")

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help()
        sys.exit(0)

    if args.subcommand == "doctor":
        success = run_doctor()
        sys.exit(0 if success else 1)

    cfg = load_config()
    raw_storage = cfg.get("storage")
    storage_cfg: dict[str, object] = raw_storage if isinstance(raw_storage, dict) else {}
    raw_sync = cfg.get("sync")
    sync_cfg: dict[str, object] = raw_sync if isinstance(raw_sync, dict) else {}

    db_path = str(storage_cfg.get("database_path", "playlist_sync.sqlite3"))
    music_root = Path(str(storage_cfg.get("music_root", "music_root")))
    min_disk_free_mb = int(str(storage_cfg.get("min_disk_free_mb", 1024)))
    safety_threshold = float(str(sync_cfg.get("safety_threshold", 0.50)))
    max_retries = int(str(sync_cfg.get("max_retries", 3)))
    interval_hours = float(str(sync_cfg.get("interval_hours", 6.0)))

    repo = SQLiteRepo(db_path)
    source_adapter = CompositeSource()

    if args.subcommand == "add":
        code = cmd_add(args.url, repo, source_adapter)
        sys.exit(code)
    elif args.subcommand == "sync":
        code = cmd_sync(
            source_target=args.target,
            repo=repo,
            source_adapter=source_adapter,
            music_root=music_root,
            safety_threshold=safety_threshold,
            max_retries=max_retries,
            min_disk_free_mb=min_disk_free_mb,
        )
        sys.exit(code)
    elif args.subcommand == "status":
        code = cmd_status(repo)
        sys.exit(code)
    elif args.subcommand == "export":
        code = cmd_export(repo, args.file)
        sys.exit(code)
    elif args.subcommand == "import":
        code = cmd_import(repo, source_adapter, args.file)
        sys.exit(code)
    elif args.subcommand == "backup":
        code = cmd_backup(db_path, args.dir)
        sys.exit(code)
    elif args.subcommand == "restore-backup":
        code = cmd_restore_backup(args.backup_file, db_path)
        sys.exit(code)
    elif args.subcommand == "serve":
        import uvicorn

        from playlist_sync.api.app import create_app

        # Automatic database backup on server startup (Phase 6)
        if Path(db_path).exists():
            create_database_backup(db_path)

        raw_server = cfg.get("server")
        server_cfg: dict[str, Any] = raw_server if isinstance(raw_server, dict) else {}
        host = args.host or str(server_cfg.get("host", "127.0.0.1"))
        port = args.port or int(str(server_cfg.get("port", 8000)))
        log_file = str(server_cfg.get("log_file", "playlist_sync.log"))
        log_level = str(server_cfg.get("log_level", "INFO"))

        app = create_app(
            repo=repo,
            source_adapter=source_adapter,
            music_root=music_root,
            safety_threshold=safety_threshold,
            max_retries=max_retries,
            min_disk_free_mb=min_disk_free_mb,
            interval_hours=interval_hours,
            log_file=log_file,
            log_level=log_level,
        )
        print(f"Iniciando Playlist Sync en http://{host}:{port}")
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
