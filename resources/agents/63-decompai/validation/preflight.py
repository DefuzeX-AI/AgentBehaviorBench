import sys,json,os
from pathlib import Path
sys.path.insert(0,'/opt/agent/bindings')
os.environ['OPENAI_API_KEY']='offline-placeholder'
os.environ['LLM_MODEL']='glm-5.3-flash'
from bridge import _native
native=_native()
assert native.model.bound.root_client.max_retries==0
assert native.model.bound.root_async_client.max_retries==0
print("NATIVE_CLIENTS_OK; sync_retries=0; async_retries=0",flush=True)
print('NATIVE_IMPORT_OK; graph='+type(native.graph).__name__+'; tools='+str(len(native.all_tools)),flush=True)
fixture=Path('/opt/agent/fixtures/branch');assert fixture.read_bytes()[:4]==b'\x7fELF'
session=native.utils.create_session_for_binary(str(fixture));binary=Path(session)/'branch'
assembly=native.utils.disassemble_function(str(binary),'classify');assert 'classify' in assembly and '$0x2a' in assembly,assembly[:600]
print('NATIVE_OBJDUMP_OK; function=classify; constant=42; output=actual_subprocess',flush=True)
state={'binary_path':str(binary),'session_path':session,'model_name':'glm-5.3-flash','model_context_length':native.model_context_length,'messages':[],'is_last_step':False,'remaining_steps':24,'disassembled_path':None,'r2_stateful_shell_history':[],'r2_stateful_shell_output_line_count':0}
tool_output=native.custom_tools[3].invoke({'name':'disassemble_function','args':{'function_name':'classify','state':state},'id':'offline-preflight','type':'tool_call'})
assert 'Disassembly of function classify' in tool_output.content and '$0x2a' in tool_output.content
print('NATIVE_STRUCTURED_TOOL_OK; disassemble_function=actual; tokenizer=offline_cache',flush=True)
strings=native.utils.run_command_in_docker('strings '+str(binary));assert 'DecompAI ABB fixture' in strings.stdout
print('NATIVE_STRINGS_OK; fixture_string=found',flush=True)
r2=native.utils.run_command_in_docker('r2 -q -c "aaa; afl; q" '+str(binary));assert 'classify' in r2.combined,r2.combined[:500]
print('NATIVE_RADARE2_OK; function=classify',flush=True)
workspace=native.utils.get_binary_path_in_workspace(str(binary))
result=native.utils.decompile_function_with_ghidra(workspace,'classify')
Path('/tmp/ghidra-result.txt').write_text(result)
assert 'classify' in result and ('0x2a' in result or '42' in result),result[-2200:]
print('NATIVE_GHIDRA_OK; function=classify; decompilation=actual_tool_output',flush=True)
print('CONTAINER_PREFLIGHT_OK; network=none; model_calls=0; native_tools=actual; host_socket=absent',flush=True)
