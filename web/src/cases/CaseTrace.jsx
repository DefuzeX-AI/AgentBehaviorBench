import { lazy, Suspense, useState } from 'react';
import { Segmented } from 'antd';
import TraceView from '../otel/TraceView.jsx';

const FlowPrototype = lazy(() => import('../flow-prototype/FlowPrototype.jsx'));

export default function CaseTrace({ run, revision }) {
  const [view, setView] = useState('otel');
  return <div className="case-trace"><Segmented value={view} onChange={setView} options={[{ label: 'OTel call tree', value: 'otel' }, { label: 'Execution flow', value: 'flow' }]} />
    {view === 'otel' ? <TraceView key={run} run={run} revision={revision} /> : <Suspense fallback={<p>Loading execution flow…</p>}><FlowPrototype key={run} run={run} revision={revision} /></Suspense>}
  </div>;
}
