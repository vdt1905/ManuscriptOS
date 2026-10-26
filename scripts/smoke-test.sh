#!/usr/bin/env bash
# Smoke test: checks every microservice through the public entry point.
#
#   bash scripts/smoke-test.sh http://localhost:8080
#   bash scripts/smoke-test.sh https://xxxx.trycloudflare.com
#
# Used by the CI/CD pipeline after each deployment; exits non-zero on failure.
set -euo pipefail

BASE="${1:-http://localhost:8080}"
BASE="${BASE%/}"
PASS=0
FAIL=0

check() {   # check <description> <expected> <actual>
  if [[ "$3" == $2 ]]; then
    echo "  PASS  $1"; PASS=$((PASS + 1))
  else
    echo "  FAIL  $1 (expected $2, got $3)"; FAIL=$((FAIL + 1))
  fi
}

status() { curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$@"; }

echo "Smoke testing $BASE"

# Wait until the Ingress answers (pods may still be starting).
for _ in $(seq 1 60); do
  [[ "$(status "$BASE/")" == "200" ]] && break
  sleep 5
done

echo "frontend"
check "home page is served"               "200" "$(status "$BASE/")"
check "deep link served by the SPA"       "200" "$(status "$BASE/dashboard")"

echo "auth-service"
check "profile without a token is refused" "401" "$(status "$BASE/api/auth/profile")"
EMAIL="smoke-$(date +%s)-$RANDOM@example.com"
SIGNUP=$(curl -s --max-time 30 -X POST "$BASE/api/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"smoke$RANDOM$RANDOM\",\"email\":\"$EMAIL\",\"password\":\"Smoke-Test-123!\"}")
TOKEN=$(printf '%s' "$SIGNUP" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
check "sign-up writes to MongoDB and returns a token" "?*" "${TOKEN:-}"
AUTH=(-H "Authorization: Bearer ${TOKEN:-none}")
check "profile with the token"             "200" "$(status "${AUTH[@]}" "$BASE/api/auth/profile")"
check "projects with the token"            "200" "$(status "${AUTH[@]}" "$BASE/api/projects")"

echo "ai-service"
check "toolkit health (public)"            "200" "$(status "$BASE/toolkit/health")"
check "DocBot without a token is refused"  "401" "$(status "$BASE/files/documents")"
check "DocBot with the token"              "200" "$(status "${AUTH[@]}" "$BASE/files/documents")"
PDF=$(curl -s --max-time 240 -X POST "$BASE/deepscan/api/v2/compile" "${AUTH[@]}" \
  -H 'Content-Type: application/json' \
  -d '{"latex":"\\documentclass{article}\\begin{document}Smoke test.\\end{document}","autofix":false,"allow_llm_repair":false}' \
  | head -c 4 || true)   # head closing the pipe early must not abort the script
check "LaTeX compiles to a PDF (tectonic)" "%PDF" "$PDF"

echo
echo "$PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
