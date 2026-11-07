// Observe already-serialized outgoing model messages. Do not modify arguments,
// headers, responses, provider selection or tool execution. Never record keys.
import {appendFileSync} from 'node:fs';
const original=globalThis.fetch;
const endpoint=process.env.ABB_AGENT_MODEL_BASE_URL.replace(/\/$/,'')+'/chat/completions';
const destination=process.env.ABB_OPENHARNESS_CALL_EVIDENCE;
globalThis.fetch=function(input,options){
  if(String(input)===endpoint && typeof options?.body==='string'){
    const body=JSON.parse(options.body);
    const calls=(body.messages??[]).flatMap(m=>m.role==='assistant'?(m.tool_calls??[]):[]);
    if(calls.length)appendFileSync(destination,JSON.stringify({calls})+'\n',{mode:0o600});
  }
  return original.call(this,input,options);
};
