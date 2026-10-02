import { Alert, Collapse, Descriptions, Skeleton, Space, Tag, Typography } from 'antd';
import useLiveJson from '../useLiveJson.js';
import SharedPreparation from './SharedPreparation.jsx';
import ReadableContent from './ReadableContent.jsx';
import GeneratedCase from './GeneratedCase.jsx';
import { selectedGeneration } from './generationModel.js';

export default function GenerationRecord({ run, revision, item, index }) {
  const { data, error } = useLiveJson(`/api/observe/runs/${run}/generation`, revision);
  const { saved, failure, imported, status } = selectedGeneration(data, item);
  const details = [
    { key: 'profile', label: 'Agent Profile sent for generation', value: data?.profile },
    { key: 'request', label: 'Saved SDK request configuration', value: data?.request },
    { key: 'selection', label: 'Batch validation & selection', value: data?.selection },
    { key: 'collection', label: 'Complete batch generation record', value: data?.collection },
    { key: 'error', label: 'Recorded generation error', value: data?.error },
    { key: 'metadata', label: 'Preparation run record', value: data?.metadata },
  ].filter(value => value.value && Object.keys(value.value).length);
  return <section className="generation-record">
    <Space wrap><Typography.Title level={4}>Preparation {index + 1}</Typography.Title>
      <Tag color={failure ? 'error' : saved ? 'success' : 'default'}>{status}</Tag>
      <Typography.Text type="secondary" copyable code>{run}</Typography.Text></Space>
    {error && <Alert type="warning" showIcon title="Unable to read generation records" description={error} />}
    {!data && !error && <Skeleton active paragraph={{ rows: 3 }} />}
    {data && <>
      <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[
        { key: 'case', label: 'Case ID', children: saved?.entry.case_id || 'Not saved' },
        { key: 'status', label: 'Preparation run', children: data.metadata.status || 'Not recorded' },
        { key: 'origin', label: 'Origin', children: imported ? 'Imported collection' : saved?.entry.origin || 'Not recorded' },
        { key: 'count', label: 'Saved / requested in batch', children: `${data.cases.length} / ${data.collection.requested_count ?? 'Not recorded'}` },
      ]} />
      {failure && <Alert type="error" showIcon title="This Case slot failed during generation" description={<ReadableContent value={failure} />} />}
      {saved && <div className="generation-case"><Typography.Title level={5}>Saved Case</Typography.Title>
        {saved.artifact ? <GeneratedCase artifact={saved.artifact} />
          : <Alert type="warning" title="The collection references this Case, but its exported file is unavailable" />}</div>}
      {!!details.length && <Collapse items={details.map(({ key, label, value }) => ({ key, label, children: <ReadableContent value={value} /> }))} />}
    </>}
    <Collapse className="generation-timing" items={[{ key: 'timing', label: 'Recorded preparation timings',
      children: <SharedPreparation run={run} revision={revision} index={index} /> }]} />
  </section>;
}
