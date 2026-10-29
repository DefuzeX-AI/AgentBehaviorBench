import {writeFileSync,appendFileSync} from 'node:fs';
const original=globalThis.fetch;let n=0;
globalThis.fetch=async function(input,options){
 if(!String(input).endsWith('/chat/completions'))return original.call(this,input,options);
 const id=String(++n).padStart(3,'0'),root=process.env.OH140_OUT;
 writeFileSync(`${root}/request-${id}.json`,options.body);
 const start=Date.now();const res=await original.call(this,input,options);
 appendFileSync(`${root}/http.jsonl`,JSON.stringify({id,status:res.status,url:String(input),elapsed_ms:Date.now()-start})+'\n');
 res.clone().arrayBuffer().then(b=>writeFileSync(`${root}/response-${id}.bin`,Buffer.from(b)));
 return res;
};
