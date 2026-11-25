"""Start a real disposable loopback Neo4j service before the ABB worker."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from neo4j import GraphDatabase
state = Path.home()/"neo4j"
for name in ("data", "logs", "run", "import", "transactions"):
    (state/name).mkdir(parents=True, exist_ok=True)
conf = Path("/var/lib/neo4j/conf/neo4j.conf")
conf.parent.mkdir(parents=True, exist_ok=True)
conf.write_text("\n".join([
    "server.default_listen_address=127.0.0.1", "server.bolt.enabled=true",
    "server.http.enabled=false", "server.https.enabled=false",
    "server.memory.heap.initial_size=256m", "server.memory.heap.max_size=384m",
    "server.memory.pagecache.size=128m", "dbms.security.procedures.unrestricted=apoc.*",
    *[f"server.directories.{name}={state/name}" for name in ("data","logs","run","import")],
])+"\n", encoding="utf-8")
password = secrets.token_urlsafe(24)
os.environ.update(NEO4J_URI="bolt://127.0.0.1:7687", NEO4J_USERNAME="neo4j", NEO4J_PASSWORD=password)
subprocess.run(["/var/lib/neo4j/bin/neo4j-admin", "dbms", "set-initial-password", password], check=True, stdout=sys.stderr)
log = (state/"startup.log").open("w")
process = subprocess.Popen(["/var/lib/neo4j/bin/neo4j", "console"], stdout=log, stderr=log)
last_error = None
for _ in range(90):
    if process.poll() is not None:
        raise RuntimeError("Neo4j exited during startup: "+(state/"startup.log").read_text())
    try:
        with GraphDatabase.driver(os.environ["NEO4J_URI"], auth=("neo4j", password), connection_timeout=2) as driver:
            driver.verify_connectivity()
        break
    except Exception as exc:
        last_error = type(exc).__name__
        time.sleep(1)
else:
    raise RuntimeError(f"Neo4j did not become ready: {last_error}")
os.chdir("/workspace")
