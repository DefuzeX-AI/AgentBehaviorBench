import { Collapse, Empty, Tag, Typography } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined } from '@ant-design/icons';
import ReadableContent from './ReadableContent.jsx';

const { Text } = Typography;

function StepStatus({ status }) {
  if (status === 'succeeded' || status === 'completed') return <Tag icon={<CheckCircleOutlined />} color="success">Succeeded</Tag>;
  if (status === 'failed' || status === 'error') return <Tag icon={<CloseCircleOutlined />} color="error">Failed</Tag>;
  if (status === 'running') return <Tag icon={<SyncOutlined spin />} color="processing">Running</Tag>;
  return <Tag>{status || 'Recorded'}</Tag>;
}

export default function CaseConversation({ inputs = [] }) {
  if (!inputs.length) return <Empty description="No recorded conversation steps" />;
  const items = inputs.map((step, index) => {
    const input = step.input || step.request || {};
    const result = step.result || step.submission || {};
    const inputId = input.input_id || result.input_id || `step-${index + 1}`;
    return { key: inputId, label: <span className="conversation-step-label"><strong>Step {index + 1}</strong><Text type="secondary">{inputId}</Text><StepStatus status={result.status} /></span>,
      children: <div className="conversation-pair">
        <article><Text className="case-eyebrow">INPUT</Text><ReadableContent value={input.payload ?? input.prompt ?? input} /></article>
        <article><Text className="case-eyebrow">AGENT OUTPUT</Text>{Object.hasOwn(result, 'output') ? <ReadableContent value={result.output} /> : <Text type="secondary">No Agent output was recorded for this step.</Text>}</article>
      </div> };
  });
  return <Collapse className="conversation-collapse" defaultActiveKey={[items[0].key]} items={items} />;
}
