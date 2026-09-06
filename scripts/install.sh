#!/usr/bin/env bash
# Deploy b2b-lead-research to multiple agent hosts via symlinks.
# Single source of truth: this directory (recommended: keep it in git).
#
# Usage:
#   scripts/install.sh            # deploy to default hosts (claude-code, codex)
#   scripts/install.sh --verify   # check existing links without changing anything
#   scripts/install.sh --hosts claude-code,codex,myagent
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_NAME="$(basename "$SKILL_DIR")"

declare -A HOST_DIRS=(
  ["claude-code"]="$HOME/.claude/skills"
  ["codex"]="$HOME/.codex/skills"
)

is_source_dir() {
  [[ -d "$1" ]] && [[ "$(cd "$1" && pwd)" == "$SKILL_DIR" ]]
}

verify_host() {
  local host="$1" dir="$2" link="$dir/$SKILL_NAME"
  if is_source_dir "$link"; then
    echo "  [source]   $host: source directory itself, nothing to link"
    return 0
  fi
  if [[ ! -e "$link" ]]; then
    echo "  [missing]  $host: no link at $link"
    return 1
  fi
  local target
  target="$(readlink "$link" 2>/dev/null || true)"
  if [[ "$target" == "$SKILL_DIR" || "$(cd "$link" && pwd)" == "$SKILL_DIR" ]]; then
    echo "  [ok]       $host: $link -> $SKILL_DIR"
    return 0
  fi
  echo "  [conflict] $host: $link points to '$target', expected '$SKILL_DIR'"
  return 1
}

deploy_host() {
  local host="$1" dir="$2" link="$dir/$SKILL_NAME"
  if is_source_dir "$link"; then
    echo "  [source]   $host: source directory itself, nothing to link"
    return 0
  fi
  if [[ -L "$link" ]]; then
    local target
    target="$(readlink "$link")"
    if [[ "$target" == "$SKILL_DIR" ]]; then
      echo "  [ok]       $host: already linked"
      return 0
    fi
    echo "  [conflict] $host: $link already points to '$target'; not touching it."
    return 1
  fi
  if [[ -e "$link" ]]; then
    echo "  [conflict] $host: $link exists and is not a symlink; refusing to overwrite."
    return 1
  fi
  mkdir -p "$dir"
  ln -s "$SKILL_DIR" "$link"
  echo "  [linked]   $host: $link -> $SKILL_DIR"
}

main() {
  local mode="deploy" hosts_arg=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --verify) mode="verify" ;;
      --hosts) hosts_arg="${2:-}"; shift ;;
      *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
  done

  local hosts=()
  if [[ -n "$hosts_arg" ]]; then
    IFS=',' read -ra hosts <<< "$hosts_arg"
  else
    hosts=(claude-code codex)
  fi

  echo "source: $SKILL_DIR"
  local failures=0
  for host in "${hosts[@]}"; do
    local dir="${HOST_DIRS[$host]:-}"
    if [[ -z "$dir" ]]; then
      echo "  [skip]     $host: unknown host (known: ${!HOST_DIRS[*]})"
      continue
    fi
    if [[ "$mode" == "verify" ]]; then
      verify_host "$host" "$dir" || failures=$((failures + 1))
    else
      deploy_host "$host" "$dir" || failures=$((failures + 1))
    fi
  done

  if [[ "$mode" == "deploy" && $failures -eq 0 ]]; then
    echo
    echo "Done. Start a NEW session in each host and confirm '$SKILL_NAME' appears in its skill list."
  fi
  exit $failures
}

main "$@"
