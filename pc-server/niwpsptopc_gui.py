"""PyInstaller-friendly entry point for the niwPSPtoPC GUI."""

from pc_server.gui import main


if __name__ == "__main__":
    raise SystemExit(main())
