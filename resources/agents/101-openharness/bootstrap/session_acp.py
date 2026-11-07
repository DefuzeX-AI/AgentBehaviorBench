"""Transport-only ACP adapter for the unchanged upstream session CLI.

Native requests supply exact tool arguments; persisted messages supply results.
No model calls, tool execution, prompt rewriting or synthesized tool evidence here.
"""
import asyncio
import json
import re
import sys
import uuid
from pathlib import Path
from acp import run_agent, text_block, RequestError
from acp.schema import InitializeResponse, NewSessionResponse, PromptResponse, AgentMessageChunk, ToolCallStart
from launch import prepare

class NativeSession:
    def __init__(self, process, home):
        self.process, self.home = process, Path(home)
        self.sid = None
        self.message_count = 0
        self.evidence_offset = 0
        self.busy = False
        self.closed = False
        self.cancelled = False
        self.drain = asyncio.create_task(self.stderr())

    async def stderr(self):
        while chunk := await self.process.stderr.read(8192):
            sys.stderr.buffer.write(chunk);sys.stderr.buffer.flush()

    async def read(self):
        line = await asyncio.wait_for(self.process.stdout.readline(), 120)
        if not line:
            raise RuntimeError('Native session ended before completing the request')
        try: return json.loads(line)
        except ValueError: raise RuntimeError('Native session emitted invalid NDJSON') from None

    async def close(self):
        if self.closed:return
        self.closed=True
        if self.process.returncode is None:
            self.process.stdin.close()
            try: await asyncio.wait_for(self.process.wait(),2)
            except asyncio.TimeoutError:
                self.process.terminate()
                try: await asyncio.wait_for(self.process.wait(),2)
                except asyncio.TimeoutError:
                    self.process.kill();await self.process.wait()
        await self.drain

    async def persisted(self, prompt):
        path=self.home/'.oh/sessions'/f'{self.sid}.json'
        for _ in range(100):
            try:
                if path.stat().st_size > 16*1024*1024:raise RuntimeError('Native session evidence exceeds 16 MiB')
                data=json.loads(path.read_text())
                messages=data['messages']
                if data['id']!=self.sid:raise RuntimeError('Native session identity mismatch')
                if len(messages)>self.message_count:
                    current=messages[self.message_count:]
                    if current[0].get('role')!='user' or current[0].get('content')!=prompt:
                        raise RuntimeError('Native session evidence does not match current prompt')
                    self.message_count=len(messages)
                    return current
            except (FileNotFoundError,json.JSONDecodeError):pass
            await asyncio.sleep(.05)
        raise RuntimeError('Native session did not persist current-turn evidence')

class Bridge:
    def __init__(self):self.sessions={}
    def on_connect(self,conn):self.conn=conn
    async def initialize(self,protocol_version,**kwargs):
        return InitializeResponse(protocol_version=1)
    async def new_session(self,cwd,mcp_servers=None,**kwargs):
        import os
        if mcp_servers:raise RequestError.invalid_params({'reason':'External MCP configuration is not provisioned'})
        if Path(cwd).resolve()!=Path.cwd().resolve():raise RequestError.invalid_params({'reason':'Session cwd must equal the configured workspace'})
        try:command,child=prepare(dict(os.environ))
        except ValueError as exc:raise RequestError(-32602,str(exc)) from None
        # Explicitly retain upstream session default trust policy, not ACP ask.
        command += ['--permission-mode','trust']
        proc=await asyncio.create_subprocess_exec(*command,cwd=cwd,env=child,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=16*1024*1024)
        session=NativeSession(proc,child['HOME'])
        try:
            ready=await session.read()
            if ready.get('type')!='ready' or not re.fullmatch(r'[a-zA-Z0-9-]+',ready.get('sessionId','')):
                raise RuntimeError('Native session did not announce a valid identity')
            session.sid=ready['sessionId'];self.sessions[session.sid]=session
            return NewSessionResponse(session_id=session.sid)
        except Exception as exc:
            await session.close();raise RequestError(-32603,str(exc)) from None
        except BaseException:
            await session.close();raise
    async def prompt(self,session_id,prompt,**kwargs):
        if session_id not in self.sessions:raise RequestError.invalid_params({'reason':'Unknown session'})
        s=self.sessions[session_id]
        if s.busy or s.closed:raise RequestError(-32600,'Session is busy or closed')
        if not prompt or any(getattr(p,'type',None)!='text' for p in prompt):raise RequestError(-32602,'Only text prompts are supported')
        value='\n\n'.join(p.text for p in prompt)
        if not value.strip():raise RequestError(-32602,'Prompt must not be empty')
        identity=uuid.uuid4().hex;s.busy=True;tool_ends=[]
        try:
            s.process.stdin.write((json.dumps({'id':identity,'prompt':value})+'\n').encode());await s.process.stdin.drain()
            while True:
                event=await s.read()
                if event.get('id')!=identity:raise RuntimeError('Native event has the wrong prompt identity')
                kind=event.get('type')
                if kind=='error':raise RuntimeError('Native session error: '+str(event.get('message','Unknown error')))
                if kind=='text':
                    await self.conn.session_update(session_id=session_id,update=AgentMessageChunk(session_update='agent_message_chunk',content=text_block(event['content'])))
                if kind=='tool_end':tool_ends.append(event)
                if kind=='turnStop':
                    if event.get('reason')!='completed':raise RuntimeError('Native session stopped: '+str(event.get('reason')))
                    break
            messages=await s.persisted(value)
            results=[r for m in messages for r in m.get('toolResults',[])]
            evidence=s.home/'model-tool-calls.jsonl'
            calls_by_id={}
            if evidence.exists():
                if evidence.stat().st_size>16*1024*1024:raise RuntimeError('Native request evidence exceeds 16 MiB')
                with evidence.open() as f:
                    f.seek(s.evidence_offset)
                    for line in f:
                        for c in json.loads(line)['calls']:
                            if c['id'] not in {r['callId'] for r in results}:continue
                            call={'id':c['id'],'toolName':c['function']['name'],'arguments':json.loads(c['function']['arguments'])}
                            if c['id'] in calls_by_id and calls_by_id[c['id']]!=call:
                                raise RuntimeError('Conflicting native tool arguments')
                            calls_by_id[c['id']]=call
                    s.evidence_offset=f.tell()
            calls=list(calls_by_id.values())
            if len(calls)!=len(results) or len(results)!=len(tool_ends):raise RuntimeError('Incomplete native tool evidence')
            by_id={r['callId']:r for r in results}
            if len(by_id)!=len(results):raise RuntimeError('Duplicate native tool result identity')
            for c in calls:
                r=by_id[c['id']]
                # Reconcile streamed outcomes without guessing the IDs missing
                # from the CLI's real-time event format.
                match=next((e for e in tool_ends if e.get('tool')==c['toolName'] and e.get('output')==r['output'] and bool(e.get('error'))==r['isError']),None)
                if match is None:raise RuntimeError('Persisted tool result disagrees with stream')
                tool_ends.remove(match)
                await self.conn.session_update(session_id=session_id,update=ToolCallStart(
                    session_update='tool_call',tool_call_id=c['id'],title=c['toolName'],status='failed' if r['isError'] else 'completed',
                    raw_input=c['arguments'],raw_output=r['output'],
                    content=[{'type':'content','content':{'type':'text','text':r['output']}}],
                    field_meta={'evidence_source':'native_request_and_persisted_session','reported_after_turn':True}))
            return PromptResponse(stop_reason='end_turn')
        except Exception as exc:
            if s.cancelled:
                await s.close();return PromptResponse(stop_reason='cancelled')
            print("session bridge: "+str(exc),file=sys.stderr,flush=True)
            await s.close()
            raise RequestError(-32603,str(exc)) from None
        except BaseException:
            await s.close();raise
        finally:s.busy=False
    async def cancel(self,session_id,**kwargs):
        s=self.sessions.get(session_id)
        if s:
            s.cancelled=True;await s.close()
    async def close(self):
        for s in self.sessions.values():await s.close()

async def serve():
    bridge=Bridge()
    try:await run_agent(bridge)
    finally:await bridge.close()
