"""Launch configurations available to outer Agent manifests."""
from . import auto, native, file_export

PROFILES = {
    "unconfigured": None, "unsupported": None,
    "native-otlp": native, "openclaw": native, "opensoul": native,
    "python-auto": auto, "node-auto": auto, "java-auto": auto,
    "file-export": file_export,
}
