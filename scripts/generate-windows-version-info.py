"""Generate PyInstaller version metadata from the package version."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pc-server"))

from pc_server import __version__  # noqa: E402


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = [int(part) for part in version.split(".")]
    if len(parts) != 3:
        raise ValueError("product version must contain major.minor.patch")
    return (*parts, 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    numeric = version_tuple(__version__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric},
    prodvers={numeric},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'niwPSPtoPC contributors'),
          StringStruct('FileDescription', 'Ultimate Wireless and Wired Gamepad'),
          StringStruct('FileVersion', '{__version__}'),
          StringStruct('InternalName', 'niwPSPtoPC'),
          StringStruct('LegalCopyright', 'MIT License'),
          StringStruct('OriginalFilename', 'niwPSPtoPC.exe'),
          StringStruct('ProductName', 'niwPSPtoPC'),
          StringStruct('ProductVersion', '{__version__}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
