"""Best-effort Windows network and firewall diagnostics."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NetworkInterface:
    name: str
    addresses: tuple[str, ...]
    profile: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class WindowsNetworkDiagnostics:
    interfaces: tuple[NetworkInterface, ...] = ()
    firewall_status: str = "Unavailable"
    vpn_detected: bool = False
    error: str | None = None

    @property
    def multiple_interfaces(self) -> bool:
        return len(self.interfaces) > 1


def collect_windows_network_diagnostics(
    port: int,
) -> WindowsNetworkDiagnostics:
    """Query native Windows cmdlets without requiring administrator rights."""
    if os.name != "nt":
        return WindowsNetworkDiagnostics(
            error="Windows diagnostics are available only on Windows."
        )

    script = rf"""
$ErrorActionPreference = "Stop"
$interfaces = @(
    Get-NetIPConfiguration |
        Where-Object {{ $_.NetAdapter.Status -eq "Up" -and $_.IPv4Address }} |
        ForEach-Object {{
            $profile = Get-NetConnectionProfile `
                -InterfaceIndex $_.InterfaceIndex `
                -ErrorAction SilentlyContinue |
                Select-Object -First 1
            [pscustomobject]@{{
                name = $_.InterfaceAlias
                description = $_.InterfaceDescription
                addresses = @($_.IPv4Address | ForEach-Object {{ $_.IPAddress }})
                profile = if ($profile) {{
                    [string]$profile.NetworkCategory
                }} else {{
                    "Unknown"
                }}
            }}
        }}
)
$matchingFilters = @(
    Get-NetFirewallPortFilter `
        -PolicyStore ActiveStore `
        -ErrorAction SilentlyContinue |
        Where-Object {{
            $_.Protocol -eq "UDP" -and
            ($_.LocalPort -eq "{port}" -or $_.LocalPort -eq "Any")
        }}
)
$matchingRules = @(
    $matchingFilters |
        Get-NetFirewallRule -ErrorAction SilentlyContinue |
        Where-Object {{
            $_.Enabled -eq "True" -and
            $_.Direction -eq "Inbound" -and
            $_.Action -eq "Allow"
        }}
)
[pscustomobject]@{{
    interfaces = $interfaces
    firewall = if ($matchingRules.Count -gt 0) {{
        "Inbound UDP {port} allow rule found"
    }} else {{
        "No enabled inbound UDP {port} allow rule found"
    }}
}} | ConvertTo-Json -Depth 5 -Compress
"""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            creationflags=creation_flags,
        )
        payload = json.loads(completed.stdout)
        raw_interfaces = payload.get("interfaces") or []
        if isinstance(raw_interfaces, dict):
            raw_interfaces = [raw_interfaces]
        interfaces = tuple(
            NetworkInterface(
                name=str(item.get("name", "Unknown")),
                description=str(item.get("description", "")),
                addresses=tuple(
                    str(address)
                    for address in item.get("addresses") or ()
                ),
                profile=str(item.get("profile", "Unknown")),
            )
            for item in raw_interfaces
            if isinstance(item, dict)
        )
        vpn_terms = ("vpn", "wireguard", "openvpn", "tap-", "tun", "tailscale")
        vpn_detected = any(
            any(
                term in f"{interface.name} {interface.description}".lower()
                for term in vpn_terms
            )
            for interface in interfaces
        )
        return WindowsNetworkDiagnostics(
            interfaces=interfaces,
            firewall_status=str(payload.get("firewall", "Unavailable")),
            vpn_detected=vpn_detected,
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        OSError,
    ) as exc:
        return WindowsNetworkDiagnostics(
            error=f"Windows network query failed: {exc}"
        )
