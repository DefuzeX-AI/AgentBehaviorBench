export function selectedGeneration(data, item) {
  const saved = (data?.cases || []).find(value => value.entry.case_index === item.case_index
    && (!item.case_id || value.entry.case_id === item.case_id));
  const failure = (data?.collection?.failures || []).find(value => value.case_index === item.case_index);
  const imported = data?.metadata?.schema === 'abb.case_collection.import.v1';
  const active = data?.collection?.active_case_index === item.case_index;
  return { saved, failure, imported, status: saved ? (imported ? 'Imported' : 'Saved')
    : failure ? 'Failed' : active ? 'Generating' : 'No saved Case for this slot' };
}

export function resultSources(run, preparationRuns = []) {
  return [...new Map([
    ...(run ? [{ value: run, label: `Execution · ${run}` }] : []),
    ...preparationRuns.filter(Boolean).map((value, index) => ({ value, label: `Case preparation ${index + 1} · ${value}` })),
  ].map(value => [value.value, value])).values()];
}
