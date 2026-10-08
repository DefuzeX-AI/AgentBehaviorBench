"""ABB binding for kaymen99/local-rag-researcher-deepseek.

Keeps upstream agent/ unchanged. Adapts the native Ollama + HuggingFace RAG
defaults to ABB's OpenAI-compatible interceptor and a baked fixed local corpus
that exercises retrieve → relevance-grade → summarize without downloading
embedding weights (fits the 1 GiB container budget).
"""

from __future__ import annotations

import os
import re
import sys
import types
from pathlib import Path
from typing import Any


_CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"


def _install_import_stubs() -> None:
    """Prevent importing heavy native optional stacks before the graph loads."""

    stubs = {
        "ollama": types.ModuleType("ollama"),
        "langchain_huggingface": types.ModuleType("langchain_huggingface"),
        "langchain_chroma": types.ModuleType("langchain_chroma"),
        "langchain_experimental": types.ModuleType("langchain_experimental"),
        "langchain_experimental.text_splitter": types.ModuleType(
            "langchain_experimental.text_splitter"
        ),
        "langchain_community": types.ModuleType("langchain_community"),
        "langchain_community.document_loaders": types.ModuleType(
            "langchain_community.document_loaders"
        ),
    }

    def _chat(**_kwargs):
        raise RuntimeError("Native ollama.chat was not patched by the ABB binding")

    stubs["ollama"].chat = _chat  # type: ignore[attr-defined]

    class _Disabled:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Native heavy dependency disabled in the ABB binding")

        @classmethod
        def from_documents(cls, *args, **kwargs):
            raise RuntimeError("Native heavy dependency disabled in the ABB binding")

    stubs["langchain_huggingface"].HuggingFaceEmbeddings = _Disabled  # type: ignore[attr-defined]
    stubs["langchain_chroma"].Chroma = _Disabled  # type: ignore[attr-defined]
    stubs["langchain_experimental.text_splitter"].SemanticChunker = _Disabled  # type: ignore[attr-defined]
    stubs["langchain_experimental"].text_splitter = stubs[  # type: ignore[attr-defined]
        "langchain_experimental.text_splitter"
    ]
    loaders = stubs["langchain_community.document_loaders"]
    loaders.CSVLoader = _Disabled  # type: ignore[attr-defined]
    loaders.PyPDFLoader = _Disabled  # type: ignore[attr-defined]
    loaders.PDFPlumberLoader = _Disabled  # type: ignore[attr-defined]
    loaders.TextLoader = _Disabled  # type: ignore[attr-defined]
    loaders.DirectoryLoader = _Disabled  # type: ignore[attr-defined]
    stubs["langchain_community"].document_loaders = loaders  # type: ignore[attr-defined]

    # Force-install stubs so partially-installed host packages cannot win.
    for name, module in stubs.items():
        sys.modules[name] = module


def _openai_chat_model():
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for ABB model interception")
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "deepseek-v4-pro"),
        temperature=0,
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


def _invoke_ollama(model, system_prompt, user_prompt, output_format=None):
    """Replace native Ollama calls with OpenAI-compatible HTTP chat."""

    import json

    del model  # ABB interceptor selects the replacement model.
    llm = _openai_chat_model()
    if output_format is not None:
        # DeepSeek direct API rejects json_schema; use json_object + Pydantic.
        schema = output_format.model_json_schema()
        llm = llm.bind(response_format={"type": "json_object"})
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{user_prompt}\n\nRespond with ONLY a JSON object that matches "
                    f"this JSON Schema:\n{json.dumps(schema)}"
                ),
            },
        ]
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        return output_format.model_validate_json(content)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    response = llm.invoke(messages)
    return response.content


def _parse_output(text):
    """Accept both DeepSeek-R1 think tags and plain model text."""

    if not isinstance(text, str):
        text = getattr(text, "content", None) or str(text)
    match = re.search(r"<think>(.*?)</think>\s*(.*)$", text, re.DOTALL)
    if match:
        return {"reasoning": match.group(1).strip(), "response": match.group(2).strip()}
    return {"reasoning": "", "response": text.strip()}


_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "are",
        "was",
        "were",
        "been",
        "have",
        "has",
        "had",
        "not",
        "any",
        "all",
        "may",
        "must",
        "only",
        "used",
        "when",
        "than",
        "then",
        "also",
        "over",
        "under",
        "about",
        "after",
        "before",
        "between",
        "during",
        "each",
        "other",
        "such",
        "their",
        "them",
        "these",
        "those",
        "through",
        "into",
        "onto",
        "per",
        "via",
    }
)


def _tokenize(text: str) -> set[str]:
    return {
        tok
        for tok in re.findall(r"[a-z0-9]+", text.lower())
        if len(tok) > 3 and tok not in _STOPWORDS
    }


def _load_fixed_corpus_documents():
    from langchain_core.documents import Document

    if not _CORPUS_DIR.is_dir():
        raise RuntimeError(f"Fixed ABB corpus directory is missing: {_CORPUS_DIR}")

    documents: list[Any] = []
    for path in sorted(_CORPUS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        documents.append(
            Document(
                page_content=text,
                metadata={"source": f"abb-fixed-corpus/{path.name}"},
            )
        )
    if not documents:
        raise RuntimeError(f"Fixed ABB corpus under {_CORPUS_DIR} contains no .md files")
    return documents


def _fixed_corpus_vector_db():
    """Lexical retriever over the baked corpus (no HF/Chroma download)."""

    corpus = _load_fixed_corpus_documents()
    tokenized = [(doc, _tokenize(doc.page_content)) for doc in corpus]

    class _Retriever:
        def __init__(self, k: int = 3):
            self._k = max(1, int(k))

        def invoke(self, query):
            q_tokens = _tokenize(str(query))
            if not q_tokens:
                return corpus[: self._k]

            scored = []
            for doc, tokens in tokenized:
                overlap = len(q_tokens & tokens)
                # Require at least two content tokens so stopword-ish noise cannot hit.
                if overlap < 2:
                    continue
                scored.append((overlap, doc))
            scored.sort(key=lambda item: item[0], reverse=True)
            if scored:
                return [doc for _, doc in scored[: self._k]]
            # Honest miss: return empty so relevance grading / web fallback run.
            return []

    class _VectorStore:
        def as_retriever(self, **kwargs):
            search_kwargs = kwargs.get("search_kwargs") or {}
            k = search_kwargs.get("k", 3)
            return _Retriever(k=k)

    return _VectorStore()


class LocalRagResearcherGraph:
    """Thin wrapper around the native compiled researcher graph."""

    def __init__(self, graph):
        self._graph = graph

    def invoke(self, value, config=None):
        config = dict(config or {})
        configurable = dict(config.get("configurable") or {})
        configurable.setdefault("max_search_queries", 2)
        configurable.setdefault("enable_web_search", bool(os.environ.get("TAVILY_API_KEY")))
        configurable.setdefault(
            "report_structure",
            (
                "Write a concise research brief with: summary, key findings, "
                "limitations, and sources. Do not invent citations."
            ),
        )
        config["configurable"] = configurable

        if isinstance(value, str):
            payload = {"user_instructions": value}
        elif isinstance(value, dict):
            if isinstance(value.get("user_instructions"), str) and value["user_instructions"].strip():
                payload = {"user_instructions": value["user_instructions"]}
            elif isinstance(value.get("message"), str) and value["message"].strip():
                payload = {"user_instructions": value["message"]}
            else:
                raise ValueError(
                    "Local RAG researcher input requires non-empty user_instructions text"
                )
        else:
            raise ValueError("Local RAG researcher input must be a string or mapping")

        result = self._graph.invoke(payload, config)
        if not isinstance(result, dict) or not isinstance(result.get("final_answer"), str):
            raise RuntimeError("Native researcher completed without a final_answer string")
        return result

    async def ainvoke(self, value, config=None):
        return self.invoke(value, config)

    def close(self):
        return None

    async def aclose(self):
        return None


def create_graph():
    """Synchronous zero-arg factory required by ABB LangGraph bindings."""

    _install_import_stubs()

    # Ensure package parents exist, then replace heavy native vector_db before import.
    import src  # noqa: F401
    import src.assistant  # noqa: F401

    vector_db_stub = types.ModuleType("src.assistant.vector_db")
    vector_db_stub.get_or_create_vector_db = _fixed_corpus_vector_db  # type: ignore[attr-defined]
    vector_db_stub.add_documents = lambda documents: _fixed_corpus_vector_db()  # type: ignore[attr-defined]
    sys.modules["src.assistant.vector_db"] = vector_db_stub

    import src.assistant.utils as utils_mod

    utils_mod.invoke_ollama = _invoke_ollama
    utils_mod.parse_output = _parse_output
    utils_mod.invoke_llm = (
        lambda model, system_prompt, user_prompt, output_format=None, temperature=0: _invoke_ollama(
            model, system_prompt, user_prompt, output_format=output_format
        )
    )

    import src.assistant.graph as graph_mod

    # graph.py imported these callables by name; patch the module globals too.
    graph_mod.invoke_ollama = _invoke_ollama
    graph_mod.parse_output = _parse_output
    graph_mod.get_or_create_vector_db = _fixed_corpus_vector_db

    return LocalRagResearcherGraph(graph_mod.researcher)
