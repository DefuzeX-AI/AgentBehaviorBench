import hashlib, json, shutil
from pathlib import Path

root=Path('\\\\?\\'+str(Path(__file__).resolve().parent))
evidence=root/'evidence'
evidence.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
gt=read(root/'gt-original.json')
case=read(root/'case.json')['cases'][0]
assert [i['payload'] for i in case['inputs']]==gt['steps']
summary={'commit':gt['commit_version'],'prompt_verbatim':True,'runs':{}}
models=[]
requests=[]
for label,folder in [('before','b'),('before-repeat','b2'),('after','a')]:
    directory=root/folder
    plan=read(next(directory.glob('suites/*/plan.json')))
    model=next(iter(plan['configuration']['agent_models'].values()))
    models.append(model)
    p=next(directory.glob('agents/*/cases/*/trajectory/*/steps/*/result.json'))
    step=p.parent
    trajectory=step.parent.parent
    d=read(p)
    assert read(step/'input.json')['payload']==gt['steps'][0]
    events=[json.loads(l) for l in (step/'framework.jsonl').read_text(encoding='utf-8').splitlines()]
    tools=[e['data'] for e in events if e.get('event') in ('span_start','span_end')]
    starts=[e['data'] for e in events if e.get('event')=='span_start']
    edits=[t for t in starts if t['name']=='edit_file']
    assert len(edits)==1
    assert edits[0]['input']=={'path':'settings.ini','old_string':'retries=3','new_string':'retries=3\ntimeout=30'}
    assert any(t.get('tool_call_id')==edits[0]['tool_call_id'] and t.get('tool_status')=='succeeded' for t in tools)
    assert all(t['name'] in ('edit_file','bash','complete_step') for t in starts)
    assert all(t['input']['command']=='od -c settings.ini | tail -n 6' for t in starts if t['name']=='bash')
    net=[json.loads(l) for l in (trajectory/'logs/network.jsonl').read_text(encoding='utf-8').splitlines()]
    reqs=[e['data'] for e in net if e['event']=='llm_request']
    assert reqs and all(not x['truncated'] for x in reqs)
    requests.append(reqs[0]['payload'])
    for source,name in [(step/'framework.jsonl',f'{label}-tools.jsonl'),(step/'input.json',f'{label}-input.json'),(step/'result.json',f'{label}-result.json'),(trajectory/'logs/network.jsonl',f'{label}-network.jsonl'),(trajectory/'workspace.json',f'{label}-workspace.json')]:
        shutil.copyfile(source,evidence/name)
    summary['runs'][label]={'suite_id':plan['suite_id'],'model':model,'manifest':read(trajectory/'manifest.json'),'agent_version':d['raw_output']['initialize']['agentInfo']['version'],'session_id':d['raw_output']['session_id'],'result_status':d['status'],'actual_model_ids':sorted({q['payload']['model'] for q in reqs}),'llm_request_count':len(reqs),'tools':tools,'output':d['output'],'workspace':read(trajectory/'workspace.json')}
assert models[0]==models[1]==models[2]
summary['model_configuration_equal']=True
request_controls=[{k:v for k,v in q.items() if k!='messages'} for q in requests]
assert request_controls[0]==request_controls[1]==request_controls[2]
summary['first_request_nonmessage_fields_equal']=True
summary['actual_request_settings']={k:v for k,v in request_controls[0].items() if k!='tools'}
for label,folder in [('before','b2'),('after','a')]:
    observations=[json.loads(l) for l in (root/'snapshots'/folder/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(observations)==2
    raw=(root/'snapshots'/folder/(observations[1]['sha256']+'.ini')).read_bytes()
    expected=b'[client]\r\nretries=3'+(b'\n' if label=='before' else b'\r\n')+b'timeout=30\r\nbackoff=2\r\n'
    assert raw==expected
    (evidence/(label+'-settings.ini')).write_bytes(raw)
    summary[label+'_file']={'sha256':hashlib.sha256(raw).hexdigest(),'hex':raw.hex(),'bare_lf':observations[1]['bare_lf'],'snapshot_observations':observations}
assert summary['before_file']['snapshot_observations'][0]['sha256']==summary['after_file']['snapshot_observations'][0]['sha256']
for arm in ('before','after'):
    summary[arm+'_binary_sha256']=hashlib.sha256((root/f'verify-reasonix14403-{arm}/agent/reasonix').read_bytes()).hexdigest()
    summary[arm+'_version']=read(root/f'version-{arm}.json')
    summary[arm+'_go_test_exit']=int((root/f'probe-{arm}.exit.txt').read_text(encoding='utf-8-sig'))
assert summary['before_go_test_exit']==1 and summary['after_go_test_exit']==0
summary['verdict']='Correct for the supplied literal single-edit defect; replace_all independently confirmed by Go regression, not the supplied prompt. matchLineEndings is a contributing bypass, not the necessary patch site.'
(root/'verification-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'verdict':summary['verdict'],'suites':{k:v['suite_id'] for k,v in summary['runs'].items()},'bare_lf_before':summary['before_file']['bare_lf'],'bare_lf_after':summary['after_file']['bare_lf']},indent=2))
suggested=json.loads(json.dumps(gt))
for location,role,explanation in zip(suggested['fault location'],
    ['contributing_literal_match_bypass','affected_replace_all_branch_independent_regression','direct_agent_execution_causal_branch'],
    ['Literal old text passes through unchanged. This contributes to the defect when the replacement branch omits normalization; the verified repair leaves this helper unchanged.',
     'The literal replace_all branch writes replacement text unchanged. Confirmed by real Go regression; the supplied edit_file prompt does not exercise this branch.',
     'The single-match literal branch writes replacement text unchanged. Directly reached by real ACP Agent calls using the exact verified prompt; the target-file patch removes the bare LF.']):
    location['role']=role
    location['verification']='fresh_agent_before_after' if 'direct_agent' in role else 'source_and_real_go_regression_confirmed'
    location['explanation']=explanation
suggested['Root cause']='Literal replacement branches do not adapt new_string to the target line ending. At a708a88a75302d2ff4391cea6a041c0072ffc618, matchLineEndings returns original text on a literal match, and applyOldStringEdit writes it unchanged. Two fresh native ACP baseline runs with the unchanged verified prompt inserted one bare LF into the CRLF fixture. A target-file-only backport of PR 14404 fixed the same Agent prompt with identical model/configuration and clean initial bytes. The prompt covers the single-match edit_file branch; independent real Go tests additionally confirm replace_all and mixed-ending behavior. matchLineEndings is a contributing bypass rather than the necessary repair location. The first fixed release is not established. No automated Judge was requested.'
suggested['verification_evidence']='REPORT.md and verification-summary.json in this experiment directory; original GT unchanged.'
(root/'case.suggested.json').write_text(json.dumps(suggested,indent=2)+'\n',encoding='utf-8')
