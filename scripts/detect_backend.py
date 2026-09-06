#!/usr/bin/env python3
"""Resolve execution backends for b2b-lead-research.

Reads a per-host capability manifest from capabilities/, layers CLI-level
detection (Agent Reach, mcporter, shell tools) on top, and prints a unified
capability map. Default mode is offline; use --doctor to query Agent Reach
channel status when installed.

The agent's own tool inventory is the most reliable host signal: pass
--host explicitly when known. Otherwise the script tries environment
markers from the manifests, and falls back to CLI-only resolution.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
CAPABILITIES_DIR = SKILL_DIR / "capabilities"
SHELL_TOOLS = ("curl", "pdftotext", "gh", "mcporter", "uvx", "dig")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="",
        help="Host identifier matching a manifest in capabilities/, e.g. claude-code or codex",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run 'agent-reach doctor --json' when agent-reach is installed",
    )
    parser.add_argument(
        "--check-linkedin",
        action="store_true",
        help="Run 'uvx mcp-server-linkedin@latest --status' to verify the LinkedIn session",
    )
    return parser.parse_args()


def run_stdout(cmd: list[str], timeout: int = 12, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


# ---------------------------------------------------------------- manifests


def load_manifests() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    if not CAPABILITIES_DIR.is_dir():
        return manifests
    for path in sorted(CAPABILITIES_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("host"):
            manifests[data["host"]] = data
    return manifests


def detect_host(manifests: dict[str, dict[str, Any]], explicit: str) -> dict[str, Any]:
    if explicit:
        if explicit in manifests:
            return {"host": explicit, "source": "cli_flag", "manifest": manifests[explicit]}
        return {"host": explicit, "source": "cli_flag", "manifest": None}

    for host, manifest in manifests.items():
        markers = manifest.get("detect_env", {})
        env_markers = markers.get("env", {})
        if all(
            (os.environ.get(name, "") != "") if required is True else (os.environ.get(name) == required)
            for name, required in env_markers.items()
        ) and env_markers:
            return {"host": host, "source": "env_marker", "manifest": manifest}

    argv0 = sys.argv[0].lower()
    for host, manifest in manifests.items():
        needles = manifest.get("detect_env", {}).get("argv0_contains", [])
        if any(needle in argv0 for needle in needles):
            return {"host": host, "source": "argv0", "manifest": manifest}

    return {"host": None, "source": "unresolved", "manifest": None}


# --------------------------------------------------------- native layer


def resolve_native_capability(manifest: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    if not manifest:
        return None
    cap = manifest.get("capabilities", {}).get(name)
    if not isinstance(cap, dict):
        return None
    resolved = dict(cap)
    resolved["origin"] = "native_manifest"
    return resolved


# ------------------------------------------------------------ CLI layer


def agent_reach_info() -> dict[str, Any]:
    path = shutil.which("agent-reach")
    if not path:
        venv_path = Path.home() / ".agent-reach-venv" / "bin" / "agent-reach"
        if venv_path.exists():
            path = str(venv_path)
    return {"available": path is not None, "cli": path}


def doctor_channels(ar: dict[str, Any]) -> dict[str, Any] | None:
    if not ar.get("cli"):
        return None
    raw = run_stdout([ar["cli"], "doctor", "--json"], timeout=18)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("channels", "results", "platforms"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def channel_is_active(channels: dict[str, Any] | None, name: str) -> bool:
    if not channels:
        return False
    channel = channels.get(name)
    if not isinstance(channel, dict):
        return False
    if channel.get("active_backend"):
        return True
    return channel.get("status") in {"ok", "active", "on", "ready"}


def linkedin_session_state() -> dict[str, Any]:
    uvx = shutil.which("uvx")
    if not uvx:
        return {"checked": False, "valid": None, "detail": "uvx not installed"}
    env = os.environ.copy()
    env["LINKEDIN_MCP_CONTAINER"] = "false"
    raw = run_stdout(["uvx", "mcp-server-linkedin@latest", "--status"], timeout=50, env=env)
    if not raw:
        return {"checked": True, "valid": False, "detail": "status command failed"}
    return {
        "checked": True,
        "valid": "session is valid" in raw.lower(),
        "detail": raw.strip().splitlines()[-1] if raw.strip() else "",
    }


def shell_fallback_capability(tool: str, invocation: str) -> dict[str, Any]:
    return {
        "backend": "shell",
        "invocation": invocation,
        "tool": tool,
        "origin": "shell_available",
    }


# ------------------------------------------------------------- build map


def build_capability_map(
    manifest: dict[str, Any] | None,
    ar: dict[str, Any],
    channels: dict[str, Any] | None,
    shell_tools: dict[str, bool],
    linkedin_state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    exa_active = channel_is_active(channels, "exa_search")
    mcporter_available = shell_tools["mcporter"]
    linkedin_session_valid = bool(linkedin_state.get("valid"))
    linkedin_channel_active = channel_is_active(channels, "linkedin")

    capability_map: dict[str, dict[str, Any]] = {}

    native_search = resolve_native_capability(manifest, "search")
    if native_search:
        capability_map["search"] = native_search
    elif exa_active:
        capability_map["search"] = {
            "backend": "external_cli",
            "tool": "mcporter",
            "invocation": 'mcporter call exa.web_search_exa query="{query}" numResults=5',
            "origin": "agent_reach_exa" if ar["available"] else "mcporter_exa",
        }
    elif mcporter_available:
        capability_map["search"] = {
            "backend": "none",
            "tool": "mcporter",
            "origin": "mcporter_installed_unverified",
            "note": "mcporter is installed but the Exa channel status is unknown. Verify once with 'mcporter call exa.web_search_exa query=\"test\" numResults=1' before relying on it; otherwise fall back to directories and public registries.",
        }
    else:
        capability_map["search"] = {
            "backend": "none",
            "origin": "no_automated_search",
            "note": "No automated search backend. Use official directories, company websites, and public registries via web_read.",
        }

    native_read = resolve_native_capability(manifest, "web_read")
    if native_read:
        capability_map["web_read"] = native_read
    elif shell_tools["curl"]:
        capability_map["web_read"] = shell_fallback_capability(
            "curl", 'curl -s "https://r.jina.ai/{url}"'
        )
    else:
        capability_map["web_read"] = {
            "backend": "none",
            "origin": "no_web_reader",
            "note": "No web reader available. Install curl or provide a native page reader.",
        }

    native_linkedin = resolve_native_capability(manifest, "linkedin")
    if native_linkedin and native_linkedin.get("backend") == "public_only":
        native_linkedin = dict(native_linkedin)
        native_linkedin["origin"] = "native_public_only"
    if linkedin_session_valid:
        capability_map["linkedin"] = {
            "backend": "external_cli",
            "tool": "mcporter",
            "invocation": 'mcporter call linkedin.search_people keywords="{query}" location="{location}"',
            "origin": "agent_reach_linkedin_mcp",
        }
    elif native_linkedin:
        capability_map["linkedin"] = native_linkedin
    elif ar["available"] and linkedin_channel_active:
        capability_map["linkedin"] = {
            "backend": "external_cli",
            "tool": "mcporter",
            "origin": "agent_reach_linkedin_configured_unverified",
            "note": "LinkedIn MCP is configured but session validity is unknown; verify with --check-linkedin before calling.",
        }
    else:
        capability_map["linkedin"] = {
            "backend": "public_only",
            "origin": "unavailable_public_only",
            "note": "No LinkedIn backend detected. Do not guess profile URLs or scrape non-public data.",
        }

    return capability_map


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    manifests = load_manifests()
    detected = detect_host(manifests, args.host)
    manifest = detected["manifest"]

    ar = agent_reach_info()
    shell_tools = {name: shutil.which(name) is not None for name in SHELL_TOOLS}
    channels = doctor_channels(ar) if args.doctor and ar["available"] else None
    linkedin_state = (
        linkedin_session_state() if args.check_linkedin else {"checked": False, "valid": None}
    )

    capability_map = build_capability_map(manifest, ar, channels, shell_tools, linkedin_state)

    warnings: list[str] = []
    if args.doctor and not ar["available"]:
        warnings.append("--doctor was requested but agent-reach is not installed.")
    if args.check_linkedin and linkedin_state.get("checked") and not linkedin_state.get("valid"):
        warnings.append(
            "LinkedIn MCP was checked, but the session is not valid. Re-run --login before LinkedIn search."
        )
    if detected["source"] == "unresolved":
        warnings.append(
            "Host could not be auto-detected and no manifest resolved; native capabilities are unknown. "
            "The agent should re-run with --host set to its own identifier."
        )
    if args.host and manifest is None:
        warnings.append(f"No manifest found for host '{args.host}'. Known hosts: {sorted(manifests)}.")

    return {
        "detected_host": detected,
        "capability_map": capability_map,
        "known_hosts": sorted(manifests),
        "agent_reach": ar,
        "channels": channels,
        "shell_tools": shell_tools,
        "linkedin_session": linkedin_state,
        "permissions_hints": (manifest or {}).get("permissions_hints", []),
        "warnings": warnings,
    }


def main() -> int:
    args = parse_args()
    print(json.dumps(build_report(args), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
