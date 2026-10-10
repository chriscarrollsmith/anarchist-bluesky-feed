#!/usr/bin/env bash
# Gate agent `git commit` on the same ruff/ty checks as CI.
set -euo pipefail

# Ensure common Windows / user install locations are visible to the hook host.
export PATH="${PATH:-}:/usr/bin:/bin:${HOME}/.local/bin:${HOME}/AppData/Local/hermes/bin:/c/Users/chris/AppData/Local/hermes/bin"

emit_json() {
  # Always emit a single JSON object so failClosed hosts never see empty stdout.
  printf '%s\n' "$1"
}

allow() {
  emit_json '{"permission":"allow"}'
  exit 0
}

deny() {
  local msg=$1
  if command -v jq >/dev/null 2>&1; then
    emit_json "$(jq -n --arg m "$msg" '{
      permission: "deny",
      user_message: $m,
      agent_message: $m
    }')"
  else
    python - "$msg" <<'PY'
import json, sys
msg = sys.argv[1]
print(json.dumps({
    "permission": "deny",
    "user_message": msg,
    "agent_message": msg,
}))
PY
  fi
  exit 0
}

trap 'deny "pre-commit checks: unexpected hook failure"' ERR

input=$(cat || true)
command=$(printf '%s' "${input:-{}}" | jq -r '.command // empty' 2>/dev/null || true)
if [[ -z "$command" ]]; then
  command='git commit'
fi

if [[ ! "$command" =~ git[[:space:]]+commit ]]; then
  allow
fi

if command -v uv >/dev/null 2>&1; then
  UV=(uv)
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV=("${HOME}/.local/bin/uv")
elif [[ -x "/c/Users/chris/AppData/Local/hermes/bin/uv" ]]; then
  UV=("/c/Users/chris/AppData/Local/hermes/bin/uv")
else
  deny 'pre-commit checks: uv not found on PATH (required for ruff/ty).'
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

run_check() {
  local label=$1
  shift
  if ! env NO_COLOR=1 "$@" >"$tmp" 2>&1; then
    local body
    body=$(tail -c 4000 "$tmp" || true)
    deny "pre-commit checks failed (${label}):
${body}"
  fi
}

run_check 'ruff check' "${UV[@]}" run ruff check .
run_check 'ruff format' "${UV[@]}" run ruff format --check .
run_check 'ty check' "${UV[@]}" run ty check

allow
