import { useState } from 'react';
import { Empty, Select, Space, Typography } from 'antd';
import ResultFileTree from './ResultFileTree.jsx';
import ResultFilePreview from './ResultFilePreview.jsx';
import { resultSources } from './generationModel.js';
import './resultFiles.css';

function remember(run, path) {
  const url = new URL(window.location.href);
  url.searchParams.set('resultRun', run);
  if (path) url.searchParams.set('resultFile', path); else url.searchParams.delete('resultFile');
  window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
}

export default function CaseResultFiles({ run, preparationRuns, revision }) {
  const sources = resultSources(run, preparationRuns);
  const params = new URLSearchParams(window.location.search);
  const [chosen, setChosen] = useState(() => sources.some(source => source.value === params.get('resultRun')) ? params.get('resultRun') : sources[0]?.value);
  const selectedRun = sources.some(source => source.value === chosen) ? chosen : sources[0]?.value;
  const [path, setPath] = useState(() => params.get('resultRun') === selectedRun ? params.get('resultFile') : null);
  if (!selectedRun) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No saved result directories are available yet" />;
  return <div className="case-result-files">
    <Space wrap className="result-files-toolbar"><Typography.Text strong>Saved result directory</Typography.Text>
      <Select aria-label="Result directory" value={selectedRun} options={sources} onChange={value => { setChosen(value); setPath(null); remember(value, null); }} /></Space>
    <Typography.Paragraph type="secondary">Browse the files saved for this Case's execution or shared preparation. Access stays within the selected result directory.</Typography.Paragraph>
    <div className="result-files-layout"><ResultFileTree key={selectedRun} run={selectedRun} revision={revision} selected={path} onSelect={value => { setPath(value); remember(selectedRun, value); }} />
      <ResultFilePreview key={`${selectedRun}:${path}`} run={selectedRun} path={path} revision={revision} /></div>
  </div>;
}
