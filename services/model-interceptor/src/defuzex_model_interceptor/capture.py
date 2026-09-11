"""Complete response capture; the memory threshold is never a content limit."""
from tempfile import SpooledTemporaryFile


class ResponseCapture:
    def __init__(self, memory_threshold: int):
        self._file = SpooledTemporaryFile(max_size=memory_threshold, mode="w+b")

    def write(self, chunk: bytes) -> None:
        self._file.write(chunk)

    def finish(self) -> bytes:
        try:
            self._file.seek(0)
            return self._file.read()
        finally:
            self.close()

    def close(self) -> None:
        self._file.close()
