import { Alert, Empty } from 'antd';
import GenerationRecord from './GenerationRecord.jsx';

export default function CaseGeneration({ item, revision }) {
  const runs = [...new Set(item.preparation_runs || [])];
  if (!runs.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No saved Case generation run is available yet" />;
  return <div className="case-generation">
    <Alert type="info" showIcon title="Case preparation before execution"
      description="These are saved generation or import records. Batch preparation is shared across Cases and is not added to this execution attempt's duration." />
    {runs.map((run, index) => <GenerationRecord key={run} run={run} revision={revision} item={item} index={index} />)}
  </div>;
}
