#!/usr/bin/env bash
# Re-run the published StructureClaw 1.1.0 OpenSees worker on fixed models, with no LLM.
# Usage (host): docker run --rm --network none -v "$PWD":/probe:ro --entrypoint bash <unit image> /probe/run.sh
set -euo pipefail
PKG=/opt/agent/agent/node_modules/@structureclaw/structureclaw
WORKER=$PKG/backend/src/agent-skills/analysis/runtime/worker.py
echo "structureclaw $(node -p "require('$PKG/package.json').version"); openseespy $(python -c 'import openseespy.opensees as o; print(o.version())' 2>/dev/null | tail -1)"
# Native beam template, built by the package's own builder from the same draft parameters.
(cd "$PKG" && node --input-type=module -e "
import {buildLegacyModel} from '$PKG/dist/backend/agent-runtime/legacy.js';
console.log(JSON.stringify(buildLegacyModel({inferredType:'beam',lengthM:6,loadKN:10,supportType:'simply-supported',loadType:'distributed',loadPosition:'full-span'})));") > /tmp/native-beam-template-model.json
for model in /probe/run-34dd3a64-model.json /tmp/native-beam-template-model.json \
             /probe/control-run-model-load-kN.json /probe/control-run-model-load-kN-midspan-node.json; do
  echo "=== $(basename "$model")"
  [[ $model == /tmp/* ]] && cat "$model"
  python -c "import json,sys; print(json.dumps({'action':'analyze','input':{'type':'static','model':json.load(open(sys.argv[1])),'parameters':{},'engineId':'builtin-opensees'}}))" "$model" \
    | python "$WORKER" 2>/dev/null \
    | python -c "import json,sys; r=json.load(sys.stdin); d=r['data']['data']; print(json.dumps({k: d[k] for k in ('analysisMode','plane','displacements','forces','reactions')}))"
done
