import json, zipfile, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for manifest in sorted((root/'resources/agents').glob('*/ground_truth/manifest.json')):
    doc=json.loads(manifest.read_text(encoding='utf-8'))
    if sys.argv[1:] and doc['agent_id'] not in sys.argv[1:]: continue
    for d in doc['defects']:
        print('\nDEFECT',d['id'])
        with zipfile.ZipFile(manifest.parent/d['observations'][0]['evidence_path']) as z:
            for name in z.namelist():
                if name.endswith('/input.json') or name.endswith('/result.json'):
                    data=json.loads(z.read(name))
                    content=data.get('payload', data.get('output',data))
                    if isinstance(content,dict) and 'messages' in content:
                        content={**content,'messages':content['messages'][-1:]}
                    print(name, json.dumps(content,ensure_ascii=False)[:14000])
            # Recover native system messages from retained model inputs, when present.
            messages=[]
            def walk(v):
                if isinstance(v,dict):
                    if (v.get('role') in ('system','developer') or v.get('type') == 'system') and isinstance(v.get('content'),str):
                        if v['content'] not in messages: messages.append(v['content'])
                    if v.get('id', []) == ['langchain','schema','messages','SystemMessage']:
                        c=v.get('kwargs',{}).get('content')
                        if isinstance(c,str) and c not in messages: messages.append(c)
                    for child in v.values(): walk(child)
                elif isinstance(v,list):
                    for child in v: walk(child)
            for name in z.namelist():
                if 'otel-payloads/' in name and name.endswith('-input.json'):
                    walk(json.loads(z.read(name)))
            print('RECORDED SYSTEM MESSAGES',json.dumps(messages,ensure_ascii=False)[:20000])
