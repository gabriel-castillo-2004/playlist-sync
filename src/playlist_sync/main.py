"""Main entrypoint for Playlist Sync."""

import sys

from playlist_sync.doctor import run_doctor


def main() -> None:
    """CLI entrypoint."""
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        success = run_doctor()
        sys.exit(0 if success else 1)
    print("Playlist Sync v0.1.0")
    print("Usa 'python -m playlist_sync.doctor' para verificar los requisitos del sistema.")


if __name__ == "__main__":
    main()
