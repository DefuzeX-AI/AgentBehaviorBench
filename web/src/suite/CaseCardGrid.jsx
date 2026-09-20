import { ArrowRightOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { Pagination, Progress, Tag, Typography } from 'antd';
import { executionLabels, isComplete } from './model.js';
import { latestTimestamp } from './tableModel.js';
import { RetryButton } from './SuiteControls.jsx';

const { Paragraph, Text, Title } = Typography;

function promptOf(item) {
  return item.description || item.prepared_case?.description || item.result?.benchmark?.steps?.[0]?.payload
    || item.benchmark?.steps?.[0]?.payload || item.recovery_reason || executionLabels[item.execution_status] || item.execution_status;
}

export default function CaseCardGrid({ cases, page, pageSize, onPage, onSelect }) {
  const pageItems = cases.slice((page - 1) * pageSize, page * pageSize);
  return <>
    <div className="case-card-grid">{pageItems.map(item => {
      const completed = isComplete(item.execution_status);
      const updated = latestTimestamp(item);
      return <article className="case-result-card" key={item.key} tabIndex={0} onClick={() => onSelect(item)}
        onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') onSelect(item); }}>
        <div className="case-card-header"><div><Text className="case-card-agent">{item.agent_id}</Text><Title level={3}>Case {item.case_index + 1}</Title></div>
          <div><Tag color={completed ? 'success' : 'processing'}>{executionLabels[item.execution_status] || item.execution_status}</Tag>
            <Tag color={item.judge_status === 'pass' ? 'success' : item.judge_status ? 'warning' : 'default'}>{item.judge_status || 'Judge pending'}</Tag></div></div>
        <Paragraph ellipsis={{ rows: 3, expandable: false }}>{promptOf(item)}</Paragraph>
        <Progress percent={completed ? 100 : ['running', 'judging', 'retrying'].includes(item.execution_status) ? 60 : 15} showInfo={false}
          status={['failed', 'exhausted', 'blocked'].includes(item.execution_status) ? 'exception' : 'normal'} strokeColor="#2f8f68" />
        <div className="case-card-meta"><Text type="secondary">{item.attempts.length} {item.attempts.length === 1 ? 'attempt' : 'attempts'}</Text>
          <Text type="secondary"><ClockCircleOutlined /> {updated ? new Date(updated).toLocaleString() : 'Time not recorded'}</Text></div>
        <div className="case-card-footer"><span onClick={event => event.stopPropagation()}><RetryButton item={item} /></span><Text className="case-card-link">View Case <ArrowRightOutlined /></Text></div>
      </article>;
    })}</div>
    <Pagination className="case-card-pagination" current={page} pageSize={pageSize} total={cases.length} showSizeChanger
      pageSizeOptions={[6, 10, 12, 24, 48]} showTotal={total => `${total} Cases`} onChange={onPage} />
  </>;
}
