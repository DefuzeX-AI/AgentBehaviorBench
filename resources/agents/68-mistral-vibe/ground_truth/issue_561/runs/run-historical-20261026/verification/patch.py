import difflib
from pathlib import Path
r=Path(__file__).resolve().parent
s=(r/'system_prompt.before.py').read_text(encoding='utf-8-sig')
a='    sections = [_resolve_system_prompt(config, experiment_manager)]\n'
b=a+'    from datetime import date\n\n    sections.append(f"Today\'s date is {date.today().isoformat()}.")\n'
assert s.count(a)==1
new=s.replace(a,b)
(r/'verify561-after/system_prompt.py').write_text(new, encoding="utf-8")
(r/'date.patch').write_text(''.join(difflib.unified_diff(s.splitlines(True),new.splitlines(True),fromfile='a/vibe/core/system_prompt.py',tofile='b/vibe/core/system_prompt.py')))

