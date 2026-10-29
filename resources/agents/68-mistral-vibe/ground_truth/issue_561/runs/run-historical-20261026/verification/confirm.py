import json,re
from pathlib import Path
r=Path('\\\\?\\'+str(Path('tmp/verify-issue561-20261026-parallel').resolve()))
p=next((r/'a').glob('agents/*/cases/*/trajectory/*/steps/*/result.json'));d=json.loads(p.read_text(encoding='utf-8'))
net=next((r/'a').glob('agents/*/cases/*/trajectory/*/logs/network.jsonl'))
req=[json.loads(x)['data']['payload'] for x in net.read_text(encoding='utf-8').splitlines() if json.loads(x)['event']=='llm_request'];assert len(req)==1
expected=json.loads((r/'after-request.json').read_text(encoding='utf-8'))
normalize=lambda x:re.sub(r'/tmp/vibe-scratchpad-[^`]+','/tmp/SESSION',json.dumps(x))
assert normalize(req[0])==normalize(expected)
events=[json.loads(x) for x in (p.parent/'framework.jsonl').read_text(encoding='utf-8').splitlines()]
assert not [e for e in events if e['event'] in ['span_start','span_end']]
assert d['output']=='2026-10-26';assert d['raw_output']['initialize']['agentInfo']['version']=='2.10.1'
assert 'Suite execution: COMPLETED' in (r/'after-valid.log').read_text(encoding='utf-8',errors='replace')
result={'suite_id':'suite_6c3ab8b3edbc478f9f0fd8f3b7c0a190','output':d['output'],'version':'2.10.1','request_count':1,'tool_calls':0,'request_equal_to_successful_after_except_session_scratchpad':True,'host_status':'COMPLETED','exit_code':0,'image':'defuzex-agentbench/verify561-after:e8ed832b3a71ce706f674d1cf22474fd11d89353ceb2dc7cebe3ec158946860b'}
(r/'confirmation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
f=r/'REPORT.md';s=f.read_text(encoding='utf-8-sig').replace('its final status is recorded in `confirmation.json` when available.','it also completed successfully (exit 0), answering `2026-10-26` with one model request and no tool calls. Suite: `suite_6c3ab8b3edbc478f9f0fd8f3b7c0a190`. Its request equals the first successful after request apart from the session scratchpad path. See `confirmation.json`.');f.write_text(s,encoding='utf-8')
print(json.dumps(result,indent=2))
