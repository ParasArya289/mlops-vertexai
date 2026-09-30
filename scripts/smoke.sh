#!/usr/bin/env bash
# End-to-end check of the local release path:
#   train -> gate -> register -> promote -> deploy -> serve -> degraded modes -> promote again -> rollback.
# The registry and deploy dir are isolated under .smoke/. It still overwrites data/data.csv, clears
# logs/*.jsonl, and uses the same Compose project and ports, so it stops a stack you started with
# `make bootstrap`. Run `make down` first if you care about that stack.
# Used by `make smoke` and by CI, so both run the identical check.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python}

WORK="$PWD/.smoke"
rm -rf "$WORK" && mkdir -p "$WORK"
export REGISTRY_DIR="$WORK/registry" DEPLOY_DIR="$WORK/deployed"
cleanup() {
  code=$?
  if [ "$code" -ne 0 ]; then  # show why before the evidence is torn down
    echo "== smoke test FAILED (exit $code); container state and logs:"
    docker compose ps -a 2>&1 || true
    docker compose logs --tail 40 2>&1 || true
  fi
  docker compose down -v >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

release() {  # copy champion into the deploy dir and recreate the containers
  for m in clf uplift; do $PY -m src.registry deploy $m >/dev/null; done
  docker compose up -d --build --force-recreate --wait --wait-timeout 180 >/dev/null
}
served_versions() {
  echo "$(curl -sf localhost:8081/health | $PY -c 'import json,sys; print(json.load(sys.stdin)["model_version"])')" \
       "$(curl -sf localhost:8082/health | $PY -c 'import json,sys; print(json.load(sys.stdin)["model_version"])')"
}
expect_versions() {
  got=$(served_versions)
  [ "$got" = "$1 $1" ] || { echo "FAIL: expected clf/uplift both serving $1, got: $got"; exit 1; }
  echo "serving $1 (clf and uplift)"
}

mkdir -p logs && rm -f logs/*.jsonl
$PY -m src.make_data

echo "== release v1"
$PY -m src.pipeline
for m in clf uplift; do $PY -m src.registry promote $m >/dev/null; done
release
expect_versions v1

resp=$(curl -sf -X POST localhost:8080/recommend -H 'content-type: application/json' \
  -d '{"age":30,"tenure_months":12,"avg_spend":80,"visits_30d":7,"is_member":1}')
echo "$resp"
$PY - "$resp" <<'PYEOF'
import json, sys
r = json.loads(sys.argv[1])
assert set(r) == {"p_convert", "uplift", "recommendation", "degraded"}, r
assert 0 <= r["p_convert"] <= 1 and r["uplift"] is not None and r["degraded"] is False, r
assert r["recommendation"] in {"treat", "do_not_treat"}, r
PYEOF
test -s logs/clf.jsonl && test -s logs/uplift.jsonl || { echo "serving logs missing"; exit 1; }

echo "== degraded modes against the real containers"
BODY='{"age":30,"tenure_months":12,"avg_spend":80,"visits_30d":7,"is_member":1}'
docker compose stop uplift >/dev/null 2>&1
resp=$(curl -sf -X POST localhost:8080/recommend -H 'content-type: application/json' -d "$BODY")
$PY -c 'import json,sys; r=json.loads(sys.argv[1]); assert r["degraded"] is True and r["uplift"] is None and r["p_convert"] is not None, r' "$resp"
echo "uplift down: 200, degraded"
docker compose stop clf >/dev/null 2>&1
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST localhost:8080/recommend -H 'content-type: application/json' -d "$BODY")
[ "$code" = "503" ] || { echo "FAIL: expected 503 with classifier down, got $code"; exit 1; }
echo "classifier down: 503"

echo "== promote v2"
$PY -m src.pipeline
for m in clf uplift; do $PY -m src.registry promote $m >/dev/null; done
release
expect_versions v2

echo "== rollback"
for m in clf uplift; do $PY -m src.registry rollback $m >/dev/null; done
release
expect_versions v1

echo "smoke test passed"
