"""Persistence and validation helpers shared by the Windows GUI and tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ipaddress
import json
import os
from pathlib import Path


APP_NAME = "niwPSPtoPC"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 47999


@dataclass(frozen=True, slots=True)
class GuiSettings:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allowed_hosts: tuple[str, ...] = ()


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home()))
    return base / APP_NAME / "settings.json"


def load_settings(path: Path | None = None) -> GuiSettings:
    target = path or settings_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        allowed_hosts = data.get("allowed_hosts", [])
        if not isinstance(allowed_hosts, list):
            raise ValueError("allowed_hosts must be a list")
        return validate_bind_settings(
            str(data.get("host", DEFAULT_HOST)),
            str(data.get("port", DEFAULT_PORT)),
            ", ".join(str(value) for value in allowed_hosts),
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return GuiSettings()


def save_settings(settings: GuiSettings, path: Path | None = None) -> None:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(settings), indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def validate_bind_settings(
    host_text: str,
    port_text: str,
    allowed_hosts_text: str = "",
) -> GuiSettings:
    host = host_text.strip()
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError as exc:
        raise ValueError("The listening address must be a valid IPv4 address.") from exc

    try:
        port = int(port_text.strip(), 10)
    except ValueError as exc:
        raise ValueError("The port must be a number.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("The port must be between 1 and 65535.")

    allowed_hosts: list[str] = []
    seen: set[str] = set()
    for value in allowed_hosts_text.replace(";", ",").split(","):
        candidate = value.strip()
        if not candidate:
            continue
        try:
            allowed = str(ipaddress.IPv4Address(candidate))
        except ipaddress.AddressValueError as exc:
            raise ValueError(
                f"The allowed PSP address is not a valid IPv4 address: {candidate}"
            ) from exc
        if allowed not in seen:
            allowed_hosts.append(allowed)
            seen.add(allowed)
    return GuiSettings(str(address), port, tuple(allowed_hosts))
