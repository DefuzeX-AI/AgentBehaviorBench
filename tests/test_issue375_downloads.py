"""Exercise the real build-only shell downloader without network/model calls."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
UNIT=Path(os.environ.get('ABB_DOWNLOAD_TEST_UNIT',ROOT/'resources/agents/63-decompai'))
PAYLOAD=b'official-public-release-test-payload\n'
@pytest.fixture
def fixture(tmp_path):
 b=tmp_path/'bin';b.mkdir();state=tmp_path/'calls.json';out=tmp_path/'output with spaces.zip'
 curl=b/'curl';curl.write_text('#!'+sys.executable+'\n'+'''import os,sys,json
from pathlib import Path
a=sys.argv[1:];out=Path(a[a.index('--output')+1]);state=Path(os.environ['TEST_CURL_STATE']);calls=json.loads(state.read_text()) if state.exists() else []
calls.append({'argv':a,'offset':out.stat().st_size if out.exists() else 0});state.write_text(json.dumps(calls));payload=bytes.fromhex(os.environ['TEST_PAYLOAD_HEX']);mode=os.environ['TEST_CURL_MODE']
if mode=='always-fail':
 out.write_bytes(payload[:6]);raise SystemExit(56)
if mode=='resume' and len(calls)==1:
 out.write_bytes(payload[:6]);raise SystemExit(56)
if mode=='resume':
 assert a[a.index('--continue-at')+1]=='-' and out.read_bytes()==payload[:6]
 with out.open('ab') as f:f.write(payload[6:])
else:out.write_bytes(b'wrong-content' if mode=='bad-hash' else payload)
''');curl.chmod(0o755)
 sha=b/'sha256sum';sha.write_text('#!'+sys.executable+'\n'+'''import sys,hashlib
from pathlib import Path
expected,name=sys.stdin.read().strip().split('  ',1)
raise SystemExit(0 if hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected else 1)
''');sha.chmod(0o755)
 sleep=b/'sleep';sleep.write_text('#!/bin/sh\nexit 0\n');sleep.chmod(0o755)
 return b,state,out

def run(fixture,mode='ok',digest=None):
 b,state,out=fixture;helper=UNIT/'bootstrap/download_release.sh';assert helper.is_file(),'Build-only resumable downloader is missing'
 env={**os.environ,'PATH':str(b)+os.pathsep+os.environ['PATH'],'TEST_CURL_STATE':str(state),'TEST_PAYLOAD_HEX':PAYLOAD.hex(),'TEST_CURL_MODE':mode}
 r=subprocess.run(['sh',str(helper),'https://github.com/example/project/releases/download/v1/artifact.zip',str(out),digest or hashlib.sha256(PAYLOAD).hexdigest()],capture_output=True,text=True,env=env,timeout=10)
 calls=json.loads(state.read_text()) if state.exists() else [];return r,calls,out

def test_verified_complete_release(fixture):
 r,c,out=run(fixture);assert r.returncode==0 and out.read_bytes()==PAYLOAD and len(c)==1 and 'SHA256_VERIFIED' in r.stderr

def test_real_partial_bytes_are_resumed(fixture):
 r,c,out=run(fixture,'resume');assert r.returncode==0 and out.read_bytes()==PAYLOAD and [x['offset'] for x in c]==[0,6]

def test_checksum_mismatch_fails_closed_without_retry(fixture):
 r,c,_=run(fixture,'bad-hash');assert r.returncode==65 and len(c)==1 and 'mismatch' in r.stderr

def test_network_failure_is_bounded_and_not_success(fixture):
 r,c,_=run(fixture,'always-fail');assert r.returncode==56 and len(c)==3

def test_invalid_digest_never_starts_network(fixture):
 r,c,_=run(fixture,digest='z'*64);assert r.returncode==64 and c==[]

def test_original_tls_and_request_limits_are_kept(fixture):
 r,c,_=run(fixture);assert r.returncode==0
 a=c[0]['argv'];assert '--insecure' not in a and '-k' not in a
 assert a[a.index('--connect-timeout')+1]=='20' and a[a.index('--max-time')+1]=='600' and a[a.index('--retry')+1]=='0'

def test_dockerfile_checks_both_release_digests_before_installation():
 s=(UNIT/'Dockerfile').read_text();assert s.count('sharing=locked sh /tmp/abb-download-release.sh')==2
 assert 'COPY bootstrap/download_release.sh /tmp/abb-download-release.sh' in s
 for d in ['7019eedc0e0e87d1f53d6b8f5fc62b898567679c5efdce7fbfc557c9e7655e90','bcda0a9de8993444766cc255964c65c042b291ddaf6c50d654e316e442b441fa']:assert d in s
 assert 'Ghidra_11.3.1_build/ghidra_11.3.1_PUBLIC_20250219.zip' in s


def test_verified_complete_cache_avoids_network(fixture):
 _,state,out=fixture;out.write_bytes(PAYLOAD)
 r,c,result=run(fixture);assert r.returncode==0 and c==[] and result.read_bytes()==PAYLOAD and 'CACHED_SHA256_VERIFIED' in r.stderr
