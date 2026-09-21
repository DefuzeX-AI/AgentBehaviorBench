import { Collapse, Empty, Typography } from 'antd';

const { Text } = Typography;

export default function CaseRawJson({ data }) {
  if (!data) return <Empty description="No raw Case artifact loaded" />;
  const entries = Object.entries(data).filter(([, value]) => value != null);
  return <Collapse items={entries.map(([key, value]) => ({ key, label: <Text strong>{key}</Text>,
    children: <pre className="case-json">{JSON.stringify(value, null, 2)}</pre> }))} />;
}
