"""Observe SSE frames without changing forwarding or imposing stream terminal rules."""
import json


class StreamEvidence:
    def __init__(self):
        self.buffer = bytearray()
        self.sequence = 0

    def feed(self, chunk):
        self.buffer.extend(chunk)
        self.buffer[:] = self.buffer.replace(b'\r\n', b'\n')
        frames = []
        while b'\n\n' in self.buffer:
            frame, _, rest = self.buffer.partition(b'\n\n')
            self.buffer[:] = rest
            data = b'\n'.join(line[5:].removeprefix(b' ') for line in frame.split(b'\n') if line.startswith(b'data:'))
            if not data or data == b'[DONE]':
                continue
            self.sequence += 1
            try:
                value = json.loads(data)
            except (ValueError, UnicodeError):
                value = {'unparsed_sse_data': data.decode('utf-8', errors='replace')}
            frames.append({'sequence': self.sequence, 'payload': value})
        if not chunk and self.buffer.strip():
            self.sequence += 1
            frames.append({'sequence': self.sequence, 'payload': {
                'incomplete_sse_frame': self.buffer.decode('utf-8', errors='replace')}})
            self.buffer.clear()
        return frames
