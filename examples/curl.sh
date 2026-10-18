#!/usr/bin/env bash
# Generate one Seedance 2.0 clip with plain HTTP: quote, submit, wait, download. Needs curl and jq.
# Usage: YIR_API_KEY=... bash examples/curl.sh
set -euo pipefail
: "${YIR_API_KEY:?set YIR_API_KEY}"
API=https://gateway.yir.ai/v1
# --fail-with-body: stop on an API error and print it, instead of polling a job that does not exist.
yir() { curl -sS --fail-with-body -A "yir-gh/seedance-2.0-api curl" -H "Authorization: Bearer $YIR_API_KEY" -H "Content-Type: application/json" "$@"; }

REQUEST='{
  "model": "bytedance/seedance-2.0",
  "input": {
    "type": "text",
    "prompt": "A bike courier in an orange rain jacket weaves through rainy neon traffic at night, handheld follow camera, rain and city sounds."
  },
  "parameters": {
    "resolution": "480p",
    "duration": 4,
    "aspect_ratio": "16:9",
    "generate_audio": true
  }
}'

ESTIMATE=$(yir "$API/videos/quotes" -d "$REQUEST" | jq -r '.expected_amount // empty')
# max_cost only guards against runaway charges (3x the estimate); you pay what the channel bills.
if [ -n "$ESTIMATE" ]; then
  echo "Estimated: \$$ESTIMATE"
  BODY=$(jq --arg cap "$(awk -v e="$ESTIMATE" 'BEGIN { printf "%.2f", e * 3 }')" '. + {max_cost: $cap}' <<<"$REQUEST")
else
  echo "Estimated: not available in advance"
  BODY=$REQUEST
fi
KEY=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "gh-$(date +%s)-$RANDOM$RANDOM")
JOB=$(yir "$API/videos/generations" -H "Idempotency-Key: $KEY" -d "$BODY" | jq -r .id)
echo "Job $JOB"

# Long-poll: each request returns as soon as the status changes, or after 20 seconds.
while :; do
  RESULT=$(yir "$API/jobs/$JOB?wait=20")
  STATUS=$(jq -r .status <<<"$RESULT")
  case $STATUS in succeeded | failed | cancelled) break ;; esac
done
[ "$STATUS" = succeeded ] || { jq .error <<<"$RESULT"; exit 1; }

mkdir -p output
i=0
jq -r '.result.files[] | "\(.url) \(.media_type | split("/")[1])"' <<<"$RESULT" | while read -r URL EXT; do
  curl -sSL --fail -o "output/$JOB-$i.$EXT" "$URL" && echo "Saved output/$JOB-$i.$EXT"
  i=$((i + 1))
done
jq -r '"Charged: $\(.billing.total_charged_by_yir) via \(.final_provider)"' <<<"$RESULT"
