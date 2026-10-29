import json,difflib,re
from pathlib import Path
r=Path('\\\\?\\'+str(Path(__file__).resolve().parent))
gt=json.loads((r/'gt-original.json').read_text()); case=json.loads((r/'case.json').read_text())['cases'][0]
assert [x['payload'] for x in case['inputs']]==gt['steps']
summary={'commit':gt['commit_version'],'prompts_unchanged':True,'runs':{}}
payloads=[]; models=[]
for arm in ['before','after']:
 results=r/('before-results' if arm=='before' else 'after-results'); plan=json.loads(next(results.glob('suites/*/plan.json')).read_text(encoding='utf-8'))
 model=list(plan['configuration']['agent_models'].values())[0]; models.append(model)
 p=next(results.glob('agents/*/cases/*/trajectory/*/steps/*/result.json')); d=json.loads(p.read_text(encoding='utf-8'))
 events=[json.loads(l) for l in (p.parent/'framework.jsonl').read_text(encoding='utf-8').splitlines()]
 net=next(results.glob('agents/*/cases/*/trajectory/*/logs/network.jsonl'))
 traffic=[json.loads(l) for l in net.read_text(encoding='utf-8').splitlines()]
 req=[e['data']['payload'] for e in traffic if e['event']=='llm_request']; assert len(req)==1
 payload=req[0]; payloads.append(payload)
 system='\n'.join(m['content'] for m in payload['messages'] if m['role']=='system')
 (r/f'{arm}-system.txt').write_text(system,encoding='utf-8')
 (r/f'{arm}-request.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
 tools=[e for e in events if e['event'] in ['span_start','span_end']]
 summary['runs'][arm]={'suite_id':plan['suite_id'],'model':model,'output':d['output'],'version':d['raw_output']['initialize']['agentInfo']['version'],'session_id':d['raw_output']['session_id'],'status':d['status'],'tools':tools,'llm_request_count':len(req),'date_line':[l for l in system.splitlines() if "Today's date is" in l],'contains_actual_date':'2026-10-26' in system,'host_completed':'Suite execution: COMPLETED' in (r/('before.log' if arm=='before' else 'after.log')).read_text(encoding='utf-8',errors='replace')}
 assert payload['model']=='openai/gpt-4.1-mini'
 assert [m['content'] for m in payload['messages'] if m['role']=='user']==gt['steps']
 assert summary['runs'][arm]['version']=='2.10.1'
 assert not tools
summary['model_configuration_equal']=models[0]==models[1]; assert models[0]==models[1]
assert {k:v for k,v in payloads[0].items() if k!='messages'} == {k:v for k,v in payloads[1].items() if k!='messages'}
normalize=lambda x: re.sub(r'/tmp/vibe-scratchpad-[^`]+', '/tmp/SESSION', x).replace("\n\nToday's date is 2026-10-26.",'')
assert normalize(payloads[0]['messages'][0]['content'])==normalize(payloads[1]['messages'][0]['content'])
summary['request_difference_only_date_and_scratchpad']=True
assert json.loads((r/'probe-after-final-image.json').read_text(encoding='utf-8-sig'))['matches_only_candidate_patch']
(r/'request.patch').write_text(''.join(difflib.unified_diff(json.dumps(payloads[0],indent=2).splitlines(True),json.dumps(payloads[1],indent=2).splitlines(True))),encoding='utf-8')
for arm in ['before','after']: summary['probe-'+arm]=json.loads((r/f'probe-{arm}.json').read_text(encoding='utf-8-sig'))
assert summary['probe-before']['matches_pinned_archive']
assert summary['runs']['before']['output']=='2024-06-14'
assert '2026-10-26' in summary['runs']['after']['output']
assert not summary['runs']['before']['contains_actual_date']
assert summary['runs']['after']['contains_actual_date']
(r/'verification-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary['runs'],indent=2))
