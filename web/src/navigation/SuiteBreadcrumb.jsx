import { Breadcrumb } from 'antd';
import { suiteRouteHref } from './suiteRoute.js';

function navigate(action) {
  return event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    action();
  };
}

export default function SuiteBreadcrumb({ agentId, caseIndex, onSuiteSelect, onAgentSelect }) {
  const isCase = caseIndex != null;
  const items = [
    { title: 'Suite overview', href: suiteRouteHref(null), onClick: navigate(onSuiteSelect) },
    isCase
      ? { title: agentId, href: suiteRouteHref({ agent_id: agentId }), onClick: navigate(() => onAgentSelect(agentId)) }
      : { title: <span aria-current="page">{agentId}</span> },
  ];
  if (isCase) items.push({ title: <span aria-current="page">Case {caseIndex + 1}</span> });
  return <Breadcrumb aria-label="Breadcrumb" items={items} />;
}
