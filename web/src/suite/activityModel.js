import { isActive } from './model.js';

export function suiteActivity(cases, jobs) {
  const active = cases.filter(item => isActive(item.execution_status));
  const preparing = jobs.filter(job => job.status === 'running'
    && !active.some(item => item.agent_id === job.agent_id));
  return { active, preparing };
}
