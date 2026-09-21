import { Collapse, Empty, Tag, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const { Text } = Typography;

function content(value) {
  if (typeof value === 'string') return value;
  return value == null ? '' : JSON.stringify(value, null, 2);
}

export default function CaseConversation({ inputs = [] }) {
  if (!inputs.length) return <Empty description="No recorded conversation steps" />;
  const items = inputs.map((step, index) => {
    const input = step.input || step.request || {};
    const result = step.result || step.submission || {};
    const inputId = input.input_id || result.input_id || `step-${index + 1}`;
    return { key: inputId, label: <span className="conversation-step-label"><strong>Step {index + 1}</strong><Text type="secondary">{inputId}</Text><Tag color={result.status === 'succeeded' || result.status === 'completed' ? 'success' : 'default'}>{result.status || 'Recorded'}</Tag></span>,
      children: <div className="conversation-pair">
        <article><Text className="case-eyebrow">INPUT</Text><ReactMarkdown remarkPlugins={[remarkGfm]}>{content(input.payload ?? input.prompt ?? input)}</ReactMarkdown></article>
        <article><Text className="case-eyebrow">AGENT OUTPUT</Text>{result.output ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{content(result.output)}</ReactMarkdown> : <Text type="secondary">No Agent output was recorded for this step.</Text>}</article>
      </div> };
  });
  return <Collapse className="conversation-collapse" defaultActiveKey={[items[0].key]} items={items} />;
}
