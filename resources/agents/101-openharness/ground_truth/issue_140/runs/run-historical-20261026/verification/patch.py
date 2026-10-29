from pathlib import Path
import difflib
R=Path(__file__).resolve().parent
p=R/'src/src/query/index.ts';old=p.read_text(encoding='utf-8');needle='''                streamingExecutor.addTool({ id: event.callId, toolName: event.toolName, arguments: event.arguments });
              }
              break;'''
assert old.count(needle)==1
new=old.replace(needle,needle.replace('              break;','              yield event;\n              break;'))
(R/'query.fixed.ts').write_bytes(new.encode('utf-8'))
(R/'minimal.patch').write_bytes(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/src/query/index.ts',tofile='b/src/query/index.ts')).encode('utf-8'))
