"""Authenticated, single-collection /generate API for the pinned biomedical RAG DB."""

from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse


def create_app(*, database: Path, api_key: str, nvidia_api_key: str) -> FastAPI:
    if not api_key or len(api_key) < 32:
        raise ValueError("RAG_API_KEY must be a generated secret of at least 32 characters")
    if not nvidia_api_key:
        raise ValueError("NVIDIA_API_KEY is required for NVIDIA embedding and generation")

    # Import the NVIDIA stack only after the launcher has established secret
    # redaction and selected the verified local Milvus Lite database.
    os.environ["NVIDIA_API_KEY"] = nvidia_api_key
    os.environ["NGC_API_KEY"] = nvidia_api_key
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

    from nvidia_rag import NvidiaRAG
    from nvidia_rag.utils.configuration import NvidiaRAGConfig
    from scripts.biomedical_milvus_options import configure_milvus_lite_connections

    configure_milvus_lite_connections()
    config = NvidiaRAGConfig()
    config.vector_store.name = "milvus"
    config.vector_store.url = str(database.resolve())
    config.embeddings.model_name = "nvidia/nemotron-3-embed-1b"
    config.embeddings.dimensions = 2048
    config.embeddings.server_url = "https://integrate.api.nvidia.com/v1"
    config.llm.model_name = "nvidia/nemotron-3-super-120b-a12b"
    config.ranking.enable_reranker = False
    rag = NvidiaRAG(config=config)

    app = FastAPI(title="Private Biomedical RAG bridge", docs_url=None, redoc_url=None)

    @app.get("/health")
    @app.get("/v1/health")
    async def health(authorization: str | None = Header(default=None)) -> dict[str, str]:
        _authorize(authorization, api_key)
        return {"status": "ok", "collection": "Biomedical_Dataset"}

    async def generate(
        payload: dict[str, Any], authorization: str | None = Header(default=None)
    ) -> StreamingResponse:
        _authorize(authorization, api_key)
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=422, detail="messages must be a non-empty list")
        if payload.get("use_knowledge_base") is not True:
            raise HTTPException(status_code=400, detail="knowledge-base-only mode is required")
        # NVIDIA's native endpoint uses collection_names; AIRA's pinned tool
        # speaks collection_name. Accept only the verified, one-PDF collection.
        collection = payload.get("collection_name", "Biomedical_Dataset")
        if collection != "Biomedical_Dataset":
            raise HTTPException(status_code=403, detail="collection is not enabled")

        async def stream():
            result = await rag.generate(
                messages=messages,
                use_knowledge_base=True,
                collection_names=["Biomedical_Dataset"],
                enable_citations=payload.get("enable_citations") is True,
                enable_reranker=False,
                enable_query_rewriting=False,
                enable_filter_generator=False,
                enable_streaming=True,
                vdb_top_k=3,
                reranker_top_k=3,
            )
            async for event in result.generator:
                yield event

        return StreamingResponse(stream(), media_type="text/event-stream")

    # AIRA's configured base URL ends in /v1; upstream defaults may call /generate.
    app.post("/generate")(generate)
    app.post("/v1/generate")(generate)
    app.state.rag = rag
    return app


def _authorize(header: str | None, expected: str) -> None:
    supplied = header.removeprefix("Bearer ") if header and header.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
