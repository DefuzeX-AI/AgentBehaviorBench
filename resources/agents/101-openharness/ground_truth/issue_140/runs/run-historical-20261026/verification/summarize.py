import json,hashlib,difflib
from pathlib import Path
R=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def coverage(arm,rel,needle):
    text=(R/arm/'runtime'/rel).read_text(encoding='utf-8');offset=text.index(needle)
    findings=[]
    for p in (R/arm/'coverage').glob('*.json'):
        for script in read(p)['result']:
            if not script['url'].endswith('/'+rel):continue
            ranges=[(r,f['functionName']) for f in script['functions'] for r in f['ranges'] if r['startOffset']<=offset<r['endOffset']]
            if ranges:
                rg,fn=min(ranges,key=lambda v:v[0]['endOffset']-v[0]['startOffset'])
                findings.append({'script':script['url'],'function':fn,'needle':needle,'generated_line':text[:offset].count('\n')+1,'range':rg})
    return findings
summary={}
gt=read(R/'case.original.json')
for arm in ['before','after']:
    d=R/arm;events=[json.loads(l) for l in (d/'events.jsonl').read_text(encoding='utf-8').splitlines()]
    requests=[]
    for p in sorted(d.glob('request-*.json')):
        body=read(p);known=set();orphans=[]
        for m in body['messages']:
            known.update(tc['id'] for tc in m.get('tool_calls',[]))
            if m['role']=='tool' and m['tool_call_id'] not in known:orphans.append(m['tool_call_id'])
        requests.append({'file':str(p.relative_to(R)),'sha256':sha(p),'model':body['model'],'user_messages':[m['content'] for m in body['messages'] if m['role']=='user'],'assistant_tool_call_count':sum(len(m.get('tool_calls',[])) for m in body['messages']),'tool_results':sum(m['role']=='tool' for m in body['messages']),'orphan_tool_ids':orphans})
    states=[]
    for i in [1,2]:
        state=read(d/f'state-{i}.json')
        states.append({'file':f'{arm}/state-{i}.json','session_id':state['id'],'roles':[m['role'] for m in state['messages']],'assistant_tool_calls':sum(len(m.get('toolCalls',[])) for m in state['messages']),'tool_results':sum(len(m.get('toolResults',[])) for m in state['messages'])})
    ns={};exec(compile((d/'files-2/calculator.py').read_bytes(),'calculator.py','exec'),ns)
    checks={'add_2_3':ns['add'](2,3)==5,'subtract_7_4':ns['subtract'](7,4)==3,'has_multiply':'multiply' in ns}
    if 'multiply' in ns:checks['multiply_6_7']=ns['multiply'](6,7)==42
    summary[arm]={'meta':read(d/'meta.json'),'exit':read(d/'exit.json'),'http':[json.loads(l) for l in (d/'http.jsonl').read_text().splitlines()],'requests':requests,'states':states,'prompt_equality':read(d/'meta.json')['steps']==gt['steps'],'tool_events':[e for e in events if e['type']=='tool_end'],'errors':[e for e in events if e['type']=='error'],'turn_stop':[e for e in events if e['type']=='turnStop'],'calculator_unchanged_after_second_prompt':(d/'files-1/calculator.py').read_bytes()==(d/'files-2/calculator.py').read_bytes(),'independent_file_assertions':checks,'coverage':{k:coverage(arm,*args) for k,args in {'query_complete_branch':('dist/query/index.js','streamingExecutor.addTool({ id: event.callId'),'session_complete_consumer':('dist/main.js','turnToolCalls.push({'),'session_history_rebuild':('dist/main.js','conversation.push(createAssistantMessage(assistantText'),'session_result_append':('dist/main.js','conversation.push(createToolResultMessage({ callId: tr.callId')}.items()}}
summary['controls']={'same_model':summary['before']['meta']['model']==summary['after']['meta']['model'],'both_clean':not summary['before']['meta']['initial_workspace'] and not summary['after']['meta']['initial_workspace'],'same_first_request':(R/'before/request-001.json').read_bytes()==(R/'after/request-001.json').read_bytes(),'same_main_source':sha(R/'before/runtime/src/main.tsx')==sha(R/'after/runtime/src/main.tsx'),'same_lock':sha(R/'before/runtime/package-lock.json')==sha(R/'after/runtime/package-lock.json'),'same_installed_dependencies':read(R/'before/runtime/npm-ls.json')==read(R/'after/runtime/npm-ls.json'),'query_source_diff':list(difflib.unified_diff((R/'before/runtime/src/query/index.ts').read_text(encoding='utf-8').splitlines(),(R/'after/runtime/src/query/index.ts').read_text(encoding='utf-8').splitlines()))}
(R/'verification-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({'controls':summary['controls'],'arms':{a:{'http':[x['status'] for x in summary[a]['http']],'errors':summary[a]['errors'],'states':summary[a]['states'],'checks':summary[a]['independent_file_assertions'],'coverage':summary[a]['coverage']} for a in ['before','after']}},indent=2))
