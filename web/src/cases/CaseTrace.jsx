import { lazy, Suspense, useState } from 'react';
import { Segmented } from 'antd';

const TraceView = lazy(() => import('../otel/TraceView.jsx'));
const FlowPrototype = lazy(() => import('../flow-prototype/FlowPrototype.jsx'));

export default function CaseTrace({ run, revision }) {
  const [view, setView] = useState('otel');
  return <div className="case-trace"><Segmented aria-label="Trace detail view" value={view} onChange={setView} options={[{ label: 'OTel trace', value: 'otel' }, { label: 'Execution flow', value: 'flow' }]} />
    <Suspense fallback={<p>Loading trace details…</p>}>{view === 'otel' ? <TraceView key={run} run={run} revision={revision} /> : <FlowPrototype key={run} run={run} revision={revision} />}</Suspense>
  </div>;
}
