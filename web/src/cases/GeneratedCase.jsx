import { Collapse, Space, Tag, Typography } from 'antd';
import ReadableContent from './ReadableContent.jsx';

export default function GeneratedCase({ artifact }) {
  const value = artifact.case || artifact;
  const steps = Array.isArray(value.steps) ? value.steps : [];
  return <div className="generated-case-content">
    {value.title && <Typography.Title level={5}>{value.title}</Typography.Title>}
    {value.description && <Typography.Paragraph>{value.description}</Typography.Paragraph>}
    {value.strategy_id && <Space><Tag>{value.strategy_id}{value.strategy_version ? ` @ ${value.strategy_version}` : ''}</Tag></Space>}
    {steps.map((step, index) => <section className="generated-case-step" key={step.step_id || index}>
      <Typography.Text strong>{step.step_id || `Step ${index + 1}`}</Typography.Text>
      <ReadableContent value={step.prompt ?? step.input ?? step} />
    </section>)}
    <Collapse items={[{ key: 'artifact', label: 'Complete saved Case artifact', children: <ReadableContent value={artifact} /> }]} />
  </div>;
}
