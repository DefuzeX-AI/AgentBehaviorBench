import { Tooltip } from 'antd';
import { evaluationSourceView } from './evaluationSource.js';
import './evaluationSource.css';

export default function EvaluationSourceBadge({ source, compact = false }) {
  const { label, tone, description } = evaluationSourceView(source);
  return <Tooltip title={description}>
    <span className={`evaluation-source evaluation-source-${tone}${compact ? ' evaluation-source-compact' : ''}`}
      aria-label={`Evaluator: ${label}`}>
      {!compact && <span className="evaluation-source-prefix">Evaluator</span>}
      <strong>{label}</strong>
    </span>
  </Tooltip>;
}
