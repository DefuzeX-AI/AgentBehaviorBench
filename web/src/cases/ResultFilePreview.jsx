import { Alert, Empty, Skeleton, Space, Tag, Typography } from 'antd';
import useLiveJson from '../useLiveJson.js';
import ReadableContent from './ReadableContent.jsx';

export default function ResultFilePreview({ run, path, revision }) {
  const { data, error } = useLiveJson(path ? `/api/observe/runs/${run}/file?path=${encodeURIComponent(path)}` : null, revision, false);
  if (!path) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Select a saved file to view its contents" />;
  return <section className="result-file-preview" aria-label="Result file contents">
    <Space wrap className="result-file-heading"><Typography.Text strong copyable>{path}</Typography.Text>
      {data && <Tag>{data.size.toLocaleString()} bytes</Tag>}</Space>
    {error && <Alert type="warning" showIcon title="File unavailable" description={error} />}
    {!data && !error && <Skeleton active />}
    {data?.truncated && <Alert type="info" showIcon title="Preview limited to the first 1 MiB" description="The saved file on disk is unchanged." />}
    {data && (data.binary ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="This binary or non-UTF-8 file has no text preview" />
      : /\.(json|md|markdown)$/i.test(path) && !data.truncated ? <ReadableContent key={`${run}:${path}`} value={data.text} />
        : <pre className="content-raw">{data.text}</pre>)}
  </section>;
}
