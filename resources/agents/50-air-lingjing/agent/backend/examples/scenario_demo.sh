#!/usr/bin/env bash
# Curl-only example covering scenario creation, episode execution, and data lookup.
#
# Requirements:
#   1. The backend is running at http://localhost:9909.
#   2. jq is optional and only used to format JSON output.

set -euo pipefail

HOST="${LINGJING_HOST:-http://localhost:9909}"
JQ="${JQ:-$(command -v jq || true)}"

pp() {
  if [[ -n "${JQ}" ]]; then "${JQ}" .; else cat; fi
}

echo "================================================================"
echo "[0] Inspect environments, bridges, evaluators, and the scenario schema"
echo "================================================================"
curl -s "${HOST}/api/envs"                  | pp
curl -s "${HOST}/api/envs/bridges"          | pp
curl -s "${HOST}/api/envs/evaluators"       | pp
curl -s "${HOST}/api/envs/scenarios/schema" | pp | head -n 30

echo "================================================================"
echo "[1] Create an episode from an inline ScenarioDefinition"
echo "================================================================"
CREATE_BODY=$(cat <<'JSON'
{
  "definition": {
    "sceneName": "recon_air_ground_curl",
    "collaborationType": "air-ground",
    "sceneRegion": "urban-park",
    "equipmentList": {
      "droneEntityList": [{
        "equipmentCode": "DRONE-001",
        "name": "drone1",
        "data": {"X": 0, "Y": 0, "Z": 50},
        "raw": 30,
        "sensorType": "EO/IR"
      }]
    },
    "taskMatrix": [{
      "taskLevel": "Individual",
      "task_id": "DEMO_TASK_001",
      "goal": "Move the drone close to the target point",
      "initial_state": {
        "weather": "Clear",
        "traffic": "None",
        "goalPosition": {"lon": 80, "lat": 0, "alt": 50}
      }
    }]
  }
}
JSON
)

CREATE_RESP=$(curl -s -X POST "${HOST}/api/envs/open_vocab_navigation/episodes" \
                -H 'Content-Type: application/json' \
                -d "${CREATE_BODY}")
echo "${CREATE_RESP}" | pp

TASK_ID=$(echo "${CREATE_RESP}" | python -c "import sys,json; print(json.load(sys.stdin)['data']['task_id'])")
echo "task_id = ${TASK_ID}"

echo "================================================================"
echo "[2] Execute one manual step"
echo "================================================================"
curl -s -X POST "${HOST}/api/envs/episodes/${TASK_ID}/step" \
  -H 'Content-Type: application/json' \
  -d '{"action": {"offset": [20.0, 0.0], "speed": 25}}' | pp

echo "================================================================"
echo "[3] Run automatically (falls back to a heuristic without AI_API_KEY)"
echo "================================================================"
curl -s -X POST "${HOST}/api/envs/episodes/${TASK_ID}/run" \
  -H 'Content-Type: application/json' \
  -d '{"max_steps": 12}' | pp

echo "================================================================"
echo "[4] Query realtime data for this task_id"
echo "================================================================"
sqlite3 -header -column data/stream.db \
  "SELECT id, task_id, substr(data, 1, 80) AS preview \
   FROM sim_data WHERE task_id = '${TASK_ID}' ORDER BY id;"

echo "================================================================"
echo "[5] Close the episode"
echo "================================================================"
curl -s -X DELETE "${HOST}/api/envs/episodes/${TASK_ID}" | pp
