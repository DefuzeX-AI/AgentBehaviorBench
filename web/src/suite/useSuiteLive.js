import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { actions } from './store.js';

// Serial polling avoids overlapping reads. Redux rejects older server revisions.
export default function useSuiteLive(endpoint, refresh) {
  const dispatch = useDispatch();
  const state = useSelector(store => store.suite);
  useEffect(() => {
    dispatch(actions.endpointChanged(endpoint));
    if (!endpoint) return;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const response = await fetch(endpoint, { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error(`读取 Suite 失败 HTTP ${response.status}`);
        const snapshot = await response.json();
        if (!Array.isArray(snapshot.jobs)) throw new Error('Suite 返回的数据缺少 Case 列表');
        if (!controller.signal.aborted) dispatch(actions.snapshotReceived({ snapshot, updated: new Date().toLocaleTimeString('zh-CN') }));
      } catch (error) {
        if (!controller.signal.aborted) dispatch(actions.connectionFailed(error.message));
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 1000);
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [endpoint, refresh, dispatch]);
  return { data: state.snapshot, error: state.error, updated: state.updated };
}
