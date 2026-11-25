"""Real local CPU embeddings for FrontAgent's native semantic retrieval."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from fastembed import TextEmbedding

NAME = 'BAAI/bge-small-en-v1.5'
model = TextEmbedding(NAME, cache_dir='/opt/frontagent-embeddings', threads=1,
    providers=['CPUExecutionProvider'], local_files_only=True)

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        self.send_json(200 if self.path == '/health' else 404, {'model': NAME})
    def do_POST(self):
        if self.path != '/v1/embeddings':
            return self.send_json(404, {'error': 'Unknown endpoint'})
        try:
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if data.get('model') != NAME or data.get('dimensions', 384) != 384:
                raise ValueError('Expected configured local model and 384 dimensions')
            texts = data['input']
            if isinstance(texts, str):
                texts = [texts]
            if not isinstance(texts, list) or not all(isinstance(t, str) for t in texts):
                raise ValueError('Expected text input')
            vectors = list(model.embed(texts, batch_size=4))
            self.send_json(200, {'object': 'list', 'model': NAME, 'data': [
                {'object': 'embedding', 'index': i, 'embedding': vector.tolist()}
                for i, vector in enumerate(vectors)]})
        except (ValueError, KeyError) as exc:
            self.send_json(400, {'error': str(exc)})

HTTPServer(('127.0.0.1', 8766), Handler).serve_forever()
