import json, sys, hashlib, zipfile, inspect
from pathlib import Path
from datetime import date
from unittest.mock import Mock, patch
from importlib.metadata import version
import vibe.core.system_prompt as sp
commit='f71bfd3b8cdddbb4369c843da9c48d5f6c637ef7'
z=zipfile.ZipFile('/opt/repro-source.zip')
p=Path(sp.__file__); source=p.read_text(); upstream=z.read(f'mistral-vibe-{commit}/vibe/core/system_prompt.py').decode()
config=Mock(include_commit_signature=False,include_model_info=False,include_prompt_detail=False,include_project_context=False)
rows=[]
for d in ['2024-02-29','2030-01-02']:
 class Clock(date):
  @classmethod
  def today(cls): return cls.fromisoformat(d)
 with patch.object(sp,'_resolve_system_prompt',return_value='BASE'), patch('datetime.date',Clock):
  result=sp.get_universal_system_prompt(Mock(),config,Mock(),Mock())
 rows.append({'simulated_date':d,'prompt':result})
cli=p.parent/'prompts/cli.md'
print(json.dumps({'python':sys.executable,'python_version':sys.version,'version':version('mistral-vibe'),'source_path':str(p),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'matches_pinned_archive':source==upstream,'matches_only_candidate_patch':source==upstream.replace('    sections = [_resolve_system_prompt(config, experiment_manager)]\n', '    sections = [_resolve_system_prompt(config, experiment_manager)]\n    from datetime import date\n\n    sections.append(f"Today\'s date is {date.today().isoformat()}.")\n'),'archive_commit':commit,'template_matches_archive':cli.read_text()==z.read(f'mistral-vibe-{commit}/vibe/core/prompts/cli.md').decode(),'actual_date':date.today().isoformat(),'function_line':inspect.getsourcelines(sp.get_universal_system_prompt)[1],'controls':rows},indent=2))
