import { lazy, Suspense } from 'react';
import { Collapse, Empty, Typography } from 'antd';

const RawRunView = lazy(() => import('../RawRunView.jsx'));
const { Text, Title } = Typography;

export default function CaseToolsFiles({ run, revision, inputs = [] }) {
  const fileEvidence = inputs.map((step, index) => ({ index, evidence: step.submission?.file_evidence || step.evidence?.file_evidence })).filter(item => item.evidence);
  return <div className="case-tools-files">
    <Suspense fallback={<p>Loading tool activity…</p>}><RawRunView key={run} run={run} revision={revision} initialKinds={['tool', 'tool_call']} title="Tool activity" description="Recorded tool calls and tool execution events for this Case." /></Suspense>
    <section><Title level={3}>File evidence</Title>{fileEvidence.length ? <Collapse items={fileEvidence.map(({ index, evidence }) => ({ key: index, label: `Step ${index + 1} file evidence`, children: <pre className="case-json">{JSON.stringify(evidence, null, 2)}</pre> }))} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<Text type="secondary">No file evidence was captured for this Case.</Text>} />}</section>
  </div>;
}
