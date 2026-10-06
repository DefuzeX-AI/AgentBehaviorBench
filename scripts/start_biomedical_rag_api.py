"""Serve the verified one-paper Milvus DB to ABB's native AIRA Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path,
                        help="Verified Milvus Lite .db path from the one-PDF ingestion run")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Bind address; 0.0.0.0 is needed for Docker host-gateway access")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    database = args.database.resolve()
    # Milvus Lite's URI points to its database directory, not a regular file.
    if not database.is_dir():
        parser.error(f"Milvus Lite database directory does not exist: {database}")
    try:
        ingestion = json.loads((database.parent / "ingestion-status.json").read_text())
        retrieval = json.loads((database.parent / "retrieval.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Database directory lacks valid native ingestion/retrieval receipts: {exc}")
    documents = (ingestion.get("result") or {}).get("documents") or []
    hits = retrieval.get("results") or []
    if (ingestion.get("state") != "FINISHED" or len(documents) != 1
            or (ingestion.get("result") or {}).get("failed_documents")
            or not any(hit.get("content") and hit.get("document_name") for hit in hits)):
        parser.error("Database has no matching successful one-PDF ingest and sourced retrieval receipt")

    values = dotenv_values(ROOT / ".env")
    rag_key = os.environ.get("RAG_API_KEY") or values.get("RAG_API_KEY")
    nvidia_key = os.environ.get("NVIDIA_API_KEY") or values.get("NVIDIA_API_KEY")
    if not rag_key or len(rag_key) < 32:
        parser.error("Set a random RAG_API_KEY (at least 32 characters) in .env")
    if not nvidia_key:
        parser.error("NVIDIA_API_KEY is missing from .env")

    # Ensure child components that read environment variables see the private values.
    os.environ["RAG_API_KEY"] = rag_key
    os.environ["NVIDIA_API_KEY"] = nvidia_key
    os.environ["NGC_API_KEY"] = nvidia_key
    from scripts.start_biomedical_ingest import RedactedStream
    secrets = [value for name, value in values.items()
               if value and any(part in name for part in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    sys.stdout = RedactedStream(sys.stdout, secrets)
    sys.stderr = RedactedStream(sys.stderr, secrets)
    from scripts.biomedical_rag_api import create_app

    app = create_app(database=database, api_key=rag_key, nvidia_api_key=nvidia_key)
    print(f"Biomedical RAG API ready: database={database}; collection=Biomedical_Dataset", flush=True)
    print(f"Listening on {args.host}:{args.port}; bearer auth required; Ctrl-C stops service.", flush=True)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
