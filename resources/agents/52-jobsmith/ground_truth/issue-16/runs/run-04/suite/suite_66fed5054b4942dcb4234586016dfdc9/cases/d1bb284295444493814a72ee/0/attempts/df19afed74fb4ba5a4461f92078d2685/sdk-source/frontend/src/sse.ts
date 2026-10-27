export async function readSSE<T>(resp: Response, onEvent: (ev: T) => void) {
  if (!resp.ok || !resp.body) {
    throw new Error(`Stream request failed with HTTP ${resp.status}`)
  }
  const reader = resp.body.getReader()
  const dec = new TextDecoder()
  let buf = ""

  const emit = (chunk: string) => {
    const line = chunk.split("\n").find((l) => l.startsWith("data:"))
    if (!line) return
    try {
      onEvent(JSON.parse(line.slice(5).trim()) as T)
    } catch {
      // Ignore malformed SSE frames and keep processing later events.
    }
  }

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      emit(chunk)
    }
  }

  buf += dec.decode()
  if (buf.trim()) emit(buf)
}
