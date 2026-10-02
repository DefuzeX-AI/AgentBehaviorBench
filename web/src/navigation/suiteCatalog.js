export function suiteCatalogRows(catalog, snapshot) {
  const rows = [...(catalog?.suites || [])];
  if (!snapshot?.suite_id) return rows;
  const index = rows.findIndex(row => row.suite_id === snapshot.suite_id);
  const current = { ...(rows[index] || {}), suite_id: snapshot.suite_id,
    url: `/suite/${encodeURIComponent(snapshot.suite_id)}/`, state: snapshot.state,
    origin_suite_id: snapshot.origin_suite_id, counts: snapshot.counts,
    evaluation_source: snapshot.evaluation_source ?? rows[index]?.evaluation_source,
    agent_ids: (snapshot.jobs || []).map(job => job.agent_id) };
  if (index < 0) rows.unshift(current);
  else rows[index] = current;
  return rows;
}

export function suiteCatalogMatches(row, query) {
  return [row.suite_id, row.origin_suite_id, ...(row.agent_ids || []),
    ...(row.evaluation_source?.sdks || [])]
    .some(value => String(value || '').toLowerCase().includes(query.trim().toLowerCase()));
}

export function suiteEndpoint(pathname, fallback) {
  const match = /^\/suite\/([^/]+)\/?$/.exec(pathname);
  return match ? `/api/suites/${match[1]}/result` : fallback;
}
