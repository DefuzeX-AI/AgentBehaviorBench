"""Ingest one small pristine upstream PDF, then verify real native retrieval."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import uuid
import zipfile

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.inspect_biomedical_data import inspect_archive
from scripts.start_biomedical_ingest import RedactedStream
from scripts.biomedical_milvus_options import configure_milvus_lite_connections


def available_memory_bytes():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("Cannot determine available memory")


def choose_pdf(entries):
    pdfs = [e for e in entries if not e.is_dir() and e.filename.lower().endswith(".pdf")]
    if not pdfs:
        raise ValueError("Archive has no PDFs")
    return min(pdfs, key=lambda e: (e.file_size, e.filename))


async def run():
    values = dotenv_values(ROOT / ".env")
    key = os.environ.get("NVIDIA_API_KEY") or values.get("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY is not configured")
    secrets = [v for k, v in values.items() if v and any(t in k for t in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    secrets.append(key)
    sys.stdout = RedactedStream(sys.stdout, secrets)
    sys.stderr = RedactedStream(sys.stderr, secrets)
    os.environ["NVIDIA_API_KEY"] = key
    os.environ["NGC_API_KEY"] = key
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    free = available_memory_bytes()
    print(f"Available memory before client imports: {free / 1024**3:.2f} GiB", flush=True)
    if free < 1536 * 1024**2:
        raise RuntimeError("Less than 1.5 GiB available; refusing to submit a PDF")
    archive_path = ROOT / "cache/biomedical-rag/Biomedical_Dataset.zip"
    inspect_archive(archive_path)
    directory = ROOT / "cache/biomedical-rag" / ("one-pdf-" + uuid.uuid4().hex)
    directory.mkdir(mode=0o700)
    with zipfile.ZipFile(archive_path) as archive:
        entry = choose_pdf(archive.infolist())
        pdf = directory / Path(entry.filename).name
        with archive.open(entry) as source, pdf.open("xb") as target:
            import shutil
            shutil.copyfileobj(source, target)
    import pypdfium2
    document = pypdfium2.PdfDocument(pdf)
    pages = len(document)
    document.close()
    print(f"Selected intact PDF: {pdf.name}; bytes={pdf.stat().st_size}; pages={pages}", flush=True)
    if pages > 30:
        raise RuntimeError("Smallest PDF exceeds 30 pages; not submitted")
    # Keep all generated state in this private, unique experiment directory.
    os.environ["INGESTOR_SERVER_DATA_DIR"] = str(directory)
    os.environ["APP_NVINGEST_ENABLEPDFSPLITPROCESSING"] = "true"
    # Apply BEFORE native RAG creates any metadata, ORM, ingest or query clients.
    configure_milvus_lite_connections()
    print("Milvus connection policy: 600-second keepalive; no idle pings (probe process only)", flush=True)
    from nvidia_rag import NvidiaRAG, NvidiaRAGIngestor
    from nvidia_rag.utils.configuration import NvidiaRAGConfig
    config = NvidiaRAGConfig()
    config.vector_store.name = "milvus"
    config.vector_store.url = str(directory / "milvus.db")
    config.embeddings.model_name = "nvidia/nemotron-3-embed-1b"
    config.embeddings.dimensions = 2048
    config.embeddings.server_url = "https://integrate.api.nvidia.com/v1"
    config.nv_ingest.message_client_hostname = "127.0.0.1"
    config.nv_ingest.message_client_port = 7671
    config.nv_ingest.extract_text = True
    config.nv_ingest.extract_tables = True
    config.nv_ingest.extract_charts = True
    config.nv_ingest.extract_images = False
    config.nv_ingest.extract_infographics = False
    config.nv_ingest.enable_paged_doc_split = True
    config.ranking.enable_reranker = False
    collection = "Biomedical_Dataset"
    ingestor = NvidiaRAGIngestor(config=config, mode="lite")
    ingestor.create_collection(collection_name=collection)
    free = available_memory_bytes()
    if free < 768 * 1024**2:
        raise RuntimeError("Less than 768 MiB available after client initialization; not submitted")
    print("Submitting ONE PDF to native NV-Ingest (cloud extraction/embedding may consume NVIDIA quota).", flush=True)
    response = await ingestor.upload_documents(
        filepaths=[str(pdf)], collection_name=collection, blocking=False,
        split_options={"chunk_size": 512, "chunk_overlap": 50},
        generate_summary=False, enable_pdf_split_processing=True,
        pdf_split_processing_options={"pages_per_chunk": 1})
    task_id = response.get("task_id")
    if not task_id:
        raise RuntimeError("Native upload did not return task_id: " + json.dumps(response, default=str))
    print("Native task_id:", task_id, flush=True)
    deadline = time.monotonic() + 1200
    previous = None
    minimum_available = free
    while True:
        status = await ingestor.status(task_id)
        memory = available_memory_bytes()
        minimum_available = min(minimum_available, memory)
        state = status.get("state")
        if state != previous:
            print(f"Ingestion state: {state}; available={memory / 1024**3:.2f} GiB", flush=True)
            previous = state
        if state in ("FINISHED", "FAILED", "UNKNOWN"):
            break
        if time.monotonic() > deadline:
            raise RuntimeError("20-minute wait expired; task may still run. Do not retry automatically.")
        await asyncio.sleep(10)
    # Keep original native status locally; remove credentials if errors included them.
    encoded = json.dumps(status, indent=2, default=str)
    for secret in secrets:
        encoded = encoded.replace(secret, "[REDACTED]")
    (directory / "ingestion-status.json").write_text(encoded)
    result = status.get("result") or {}
    if state != "FINISHED" or result.get("failed_documents") or result.get("validation_errors"):
        raise RuntimeError("Native ingestion did not pass; inspect " + str(directory / "ingestion-status.json"))
    documents = ingestor.get_documents(collection_name=collection)
    if not documents.get("documents"):
        raise RuntimeError("Native inventory is empty despite finished task")
    rag = NvidiaRAG(config=config)
    citations = await rag.search(
        query="CFTR cystic fibrosis treatment", collection_names=[collection],
        vdb_top_k=3, reranker_top_k=3, enable_reranker=False,
        enable_query_rewriting=False, enable_filter_generator=False)
    evidence = citations.model_dump(mode="json")
    (directory / "retrieval.json").write_text(json.dumps(evidence, indent=2))
    hits = evidence.get("results", [])
    text_hits = [h for h in hits if h.get("content") and h.get("document_name")]
    if not text_hits:
        raise RuntimeError("Retrieval returned no sourced content")
    print(json.dumps({"ingestion": "passed", "retrieval": "passed", "task_id": task_id,
                      "collection": collection, "retrieved_chunks": len(text_hits),
                      "minimum_available_gib_polled": round(minimum_available / 1024**3, 2),
                      "artifact_directory": str(directory),
                      "note": "One-PDF infrastructure check only; not ABB smoke or answer-generation acceptance"}, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(run())
