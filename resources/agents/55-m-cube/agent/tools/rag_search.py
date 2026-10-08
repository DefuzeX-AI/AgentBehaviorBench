from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tools.doc_parser import DocumentParser


class RetrievalChunk(BaseModel):
    """Normalized chunk object used for indexing and retrieval."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(..., min_length=1)
    doc_id: str = Field(..., min_length=1)
    section: str = Field(..., min_length=1)
    page_no: int = Field(..., ge=1)
    text: str = Field(..., min_length=1)


class RetrievalHit(BaseModel):
    """Retrieval output with score and source metadata."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(..., min_length=1)
    section: str = Field(..., min_length=1)
    snippet: str = Field(..., min_length=1)
    score: float = Field(..., ge=0.0, le=1.0)
    page_no: int = Field(..., ge=1)


@dataclass(frozen=True)
class ChunkConfig:
    chunk_size_chars: int = 2800  # ~700 tokens
    chunk_overlap_chars: int = 400  # ~100 tokens


def _normalize_tokens(text: str) -> list[str]:
    # Keep Chinese/English words and numbers for similarity scoring.
    return re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", text.lower())


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    if union == 0:
        return 0.0
    return inter / union


class RAGSearchService:
    """
    MVP RAG retrieval service.
    - Parses files via DocumentParser
    - Splits to overlapping chunks
    - Uses lightweight lexical similarity for retrieval
    Interface is intentionally stable for future Chroma/FAISS replacement.
    """

    def __init__(
        self,
        *,
        parser: DocumentParser | None = None,
        chunk_config: ChunkConfig | None = None,
    ) -> None:
        self._parser = parser or DocumentParser()
        self._chunk_config = chunk_config or ChunkConfig()
        self._chunks: list[RetrievalChunk] = []
        self._chunk_token_sets: dict[str, set[str]] = {}

    def clear_index(self) -> None:
        """Reset in-memory index."""
        self._chunks = []
        self._chunk_token_sets = {}

    def build_index_from_paths(self, prior_arts_paths: list[str]) -> int:
        """
        Build chunk index from input files.
        Returns chunk count for observability.
        """
        self.clear_index()
        chunk_counter = 0
        for file_path in prior_arts_paths:
            parsed = self._parser.parse_file(file_path)
            doc_id = Path(file_path).stem
            for chunk in self._chunk_text(parsed.text):
                chunk_counter += 1
                chunk_id = f"{doc_id}_{chunk_counter}"
                chunk_obj = RetrievalChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    section="body",
                    page_no=1 if parsed.page_count is None else max(1, math.ceil(chunk_counter / max(parsed.page_count, 1))),
                    text=chunk,
                )
                self._chunks.append(chunk_obj)
                self._chunk_token_sets[chunk_id] = set(_normalize_tokens(chunk))
        return len(self._chunks)

    def retrieve(
        self,
        *,
        query: str,
        top_k: int = 5,
        min_score: float = 0.65,
    ) -> list[RetrievalHit]:
        """
        Retrieve top-k evidence chunks.
        Returns empty list when no chunk reaches threshold (for fallback path).
        """
        query_tokens = set(_normalize_tokens(query))
        scored_hits: list[tuple[float, RetrievalChunk]] = []
        for chunk in self._chunks:
            score = _jaccard_similarity(query_tokens, self._chunk_token_sets.get(chunk.chunk_id, set()))
            if score >= min_score:
                scored_hits.append((score, chunk))

        scored_hits.sort(key=lambda item: item[0], reverse=True)
        top_hits = scored_hits[:top_k]
        return [
            RetrievalHit(
                doc_id=chunk.doc_id,
                section=chunk.section,
                snippet=chunk.text[:1000],
                score=round(score, 4),
                page_no=chunk.page_no,
            )
            for score, chunk in top_hits
        ]

    def retrieval_no_hit_fallback(self, query: str) -> dict[str, Any]:
        """Standard fallback payload for OA routing when retrieval has no hit."""
        return {
            "status": "retrieval_no_hit",
            "message": "未检索到高置信证据，建议补充对比文件或降低阈值后重试。",
            "query": query,
            "suggested_action": "manual_evidence_review",
        }

    def _chunk_text(self, text: str) -> list[str]:
        """Sliding-window chunking strategy aligned with TAD overlap requirement."""
        if not text.strip():
            return []
        size = self._chunk_config.chunk_size_chars
        overlap = self._chunk_config.chunk_overlap_chars
        if overlap >= size:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_size_chars.")

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            piece = text[start:end].strip()
            if piece:
                chunks.append(piece)
            if end == len(text):
                break
            start = end - overlap
        return chunks
