"""Prepare the documented bundled source without following its external runtime alias."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,tempfile

UNIT=Path(__file__).resolve().parent
PIN='0c2398c09e318be1bb6f6a52d13e572fac7c519b'
def main():
 destination=UNIT/'agent'
 if destination.exists():raise SystemExit('agent/ exists; preserving it. Verify source-provenance.json instead.')
 with tempfile.TemporaryDirectory(prefix='decompai-source-') as temporary:
  source=Path(temporary)/'repo'
  subprocess.run(['git','clone','--no-checkout','https://github.com/louisgthier/decompai.git',str(source)],check=True)
  subprocess.run(['git','-C',str(source),'checkout','--detach',PIN],check=True)
  alias=source/'decompai_analysis_sessions'
  assert alias.is_symlink() and os.readlink(alias)=='/tmp/decompai_analysis_sessions'
  expected=json.loads((UNIT/'source-provenance.json').read_text())['regular_file_sha256']
  for name,digest in expected.items():assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
  shutil.copytree(source,destination,symlinks=True,ignore=lambda p,n: ['.git','decompai_analysis_sessions'] if Path(p)==source else ['__pycache__'])
  (destination/'decompai_analysis_sessions').mkdir()
 print('SOURCE_READY; regular_files=verified; runtime_alias=empty_directory; source=bundled')
if __name__=='__main__':main()
