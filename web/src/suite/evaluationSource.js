const names = { kuma: 'KUMA', local: 'Local' };
export const evaluatorName = sdk => names[sdk] || sdk;

export function evaluationSourceView(source) {
  const sdks = source?.sdks || [];
  const known = source?.status !== 'not_recorded' && sdks.length > 0;
  const mixed = known && (source.status === 'mixed' || sdks.length > 1);
  const partial = known && source.status === 'partial';
  const label = !known ? 'Not recorded' : mixed ? 'Mixed' : evaluatorName(sdks[0]);
  const details = [];
  if (known) details.push(`Evaluator: ${sdks.map(evaluatorName).join(', ')}`);
  else details.push('Evaluator identity was not recorded.');
  if (source?.configured_sdk) details.push(`Saved SDK selection: ${evaluatorName(source.configured_sdk)}`);
  if (source?.provider_modes?.length) details.push(`Recorded modes: ${source.provider_modes.join(', ')}`);
  if (partial) details.push('Some Cases do not record an evaluator.');
  if (mixed) details.push('Saved evaluation records contain different evaluators.');
  return { label: partial ? `${label} · partial` : label,
    tone: !known ? 'unknown' : mixed || partial ? 'mixed' : sdks[0] === 'kuma' ? 'kuma' : sdks[0] === 'local' ? 'local' : 'custom',
    description: details.join(' ') };
}
