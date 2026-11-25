"""Preinstall the exact native default encoder for network-isolated execution."""
from pathlib import Path

from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
DESTINATION = Path("/opt/models/paraphrase-multilingual-MiniLM-L12-v2")

snapshot_download(
    repo_id=MODEL,
    revision=REVISION,
    local_dir=DESTINATION,
    allow_patterns=[
        "*.json", "*.model", "model.safetensors", "1_Pooling/config.json",
    ],
)
# No device override: native automatic selection uses the installed CPU runtime.
encoder = SentenceTransformer(str(DESTINATION), local_files_only=True)
vector = encoder.encode(["你好"])
assert vector.shape == (1, 384), vector.shape
print(f"Native encoder ready: {MODEL}@{REVISION}; shape={vector.shape}; device={encoder.device}")
