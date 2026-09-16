import { useEffect, useState } from 'react';

// Serial polling: no overlapping reads, abort on navigation, preserve unchanged data.
export default function useLiveJson(url, revision, live = true) {
  const [state, setState] = useState({ data: null, error: '', updated: null });
  useEffect(() => {
    setState({ data: null, error: '', updated: null });
  }, [url]);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const response = await fetch(url, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(`Read failed with HTTP ${response.status}`);
        const data = await response.json();
        if (!controller.signal.aborted) setState(old => ({
          data: JSON.stringify(old.data) === JSON.stringify(data) ? old.data : data,
          error: '', updated: new Date().toLocaleTimeString(),
        }));
      } catch (e) {
        if (!controller.signal.aborted) setState(old => ({ ...old, error: e.message }));
      } finally {
        if (live && !controller.signal.aborted) timer = setTimeout(poll, 1000);
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [url, revision, live]);
  return state;
}
