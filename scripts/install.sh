#!/usr/bin/env bash
# Deploy b2b-lead-research to agent hosts via symlinks.
#
# WHAT THIS IS
#   A skill is installed by placing a directory named `b2b-lead-research`
#   (containing SKILL.md) inside the host's skills directory. That's all.
#   This script automates ONE variant of that: keep the git repo wherever
#   you like and link it into each host, so `git pull` upgrades every host
#   at once. It is OPTIONAL — cloning straight into the skills directory
#   works without this script (see README, 方式二).
#
#   Windows: do NOT use this script. Git Bash often implements `ln -s` as a
#   file copy, so deploy looks successful but `git pull` on the source repo
#   will not update the skills directory. Use README 方式二 instead.
#
# WHAT IT DOES
#   - Creates symlinks: ~/.claude/skills/b2b-lead-research -> this repo
#     (also ~/.codex/skills, ~/.cursor/skills, ~/.zcode/skills, ~/.workbuddy-ai/skills)
#   - Refuses to overwrite unrelated content, verifies links with --verify
#
# Usage:
#   scripts/install.sh            # deploy to default hosts (claude-code, codex, cursor, zcode, workbuddy)
#   scripts/install.sh --verify   # check existing links without changing anything
#   scripts/install.sh --hosts claude-code,codex,cursor,zcode,workbuddy
#
# Requires the directory name to be exactly `b2b-lead-research` (it becomes
# the skill ID in every host). If you downloaded a GitHub ZIP, the extracted
# folder is `b2b-lead-research-master` — rename it first, or better, git clone.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_NAME="$(basename "$SKILL_DIR")"

if [[ "$SKILL_NAME" != "b2b-lead-research" ]]; then
  echo "error: directory must be named 'b2b-lead-research' (it becomes the skill ID)."
  echo "       Found '$SKILL_NAME'. A GitHub ZIP extracts to 'b2b-lead-research-master';"
  echo "       rename it to 'b2b-lead-research' or git clone instead:"
  echo "       git clone https://github.com/fxmumu/b2b-lead-research.git"
  exit 2
fi

# Portable host registry: avoids `declare -A` (bash 4+); macOS ships bash 3.2.
KNOWN_HOSTS="claude-code codex cursor zcode workbuddy"

host_dir() {
  case "$1" in
    claude-code) echo "$HOME/.claude/skills" ;;
    codex) echo "$HOME/.codex/skills" ;;
    cursor) echo "$HOME/.cursor/skills" ;;
    zcode) echo "$HOME/.zcode/skills" ;;
    workbuddy) echo "$HOME/.workbuddy-ai/skills" ;;
    *) return 1 ;;
  esac
}

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
    hosts=(claude-code codex cursor zcode workbuddy)
  fi

  echo "source: $SKILL_DIR"
  local failures=0
  for host in "${hosts[@]}"; do
    local dir
    if ! dir="$(host_dir "$host")"; then
      echo "  [skip]     $host: unknown host (known: $KNOWN_HOSTS)"
      continue
    fi
    if [[ "$mode" == "verify" ]]; then
      verify_host "$host" "$dir" || failures=$((failures + 1))
    else
      deploy_host "$host" "$dir" || failures=$((failures + 1))
    fi
  done

  if [[ "$failures" -gt 0 ]]; then
    echo
    echo "Completed with $failures failure(s)."
  elif [[ "$mode" == "deploy" ]]; then
    local deployed_any=false
    for host in "${hosts[@]}"; do
      if host_dir "$host" >/dev/null; then
        deployed_any=true
      fi
    done
    if [[ "$deployed_any" == true ]]; then
      echo
      echo "Done. Start a NEW session in each host and confirm '$SKILL_NAME' appears in its skill list."
    else
      echo "No valid hosts specified (known: $KNOWN_HOSTS)."
      exit 2
    fi
  fi
  exit $failures
}

main "$@"
