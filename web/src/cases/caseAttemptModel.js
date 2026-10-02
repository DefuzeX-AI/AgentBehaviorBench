import { reportOf } from '../suite/model.js';

// A historical Attempt with no report must not inherit the current Case's report.
export function attemptReport(item, attempt, evaluation) {
  if (attempt) {
    const retained = reportOf(attempt);
    if (retained) return retained;
    // Recovery Attempts may share an artifact whose report is overwritten later.
    const owners = (item.attempts || []).filter(value => value.artifact_run_id === attempt.artifact_run_id);
    return attempt.artifact_run_id && owners.length === 1 && owners[0].attempt_id === attempt.attempt_id
      ? evaluation?.judge || null : null;
  }
  return item.attempts?.length ? null : reportOf(item);
}
