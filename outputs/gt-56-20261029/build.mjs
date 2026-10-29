import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const outputDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(outputDir, '../..');
const agentRoot = path.join(repoRoot, 'resources', 'agents');
const rows = [];

for (const unit of await fs.readdir(agentRoot, { withFileTypes: true })) {
  if (!unit.isDirectory()) continue;
  const gt = path.join(agentRoot, unit.name, 'ground_truth');
  let issueNames;
  try { issueNames = await fs.readdir(gt, { withFileTypes: true }); }
  catch { continue; }
  for (const entry of issueNames) {
    if (!entry.isDirectory() || !/^issue_\d+$/.test(entry.name)) continue;
    const issueDir = path.join(gt, entry.name);
    const runsDir = path.join(issueDir, 'runs');
    let hasCanonicalTrajectory = false;
    try {
      for (const run of await fs.readdir(runsDir, { withFileTypes: true })) {
        if (!run.isDirectory()) continue;
        const trajectoryDir = path.join(runsDir, run.name, 'trajectory');
        try {
          for (const attempt of await fs.readdir(trajectoryDir, { withFileTypes: true })) {
            if (!attempt.isDirectory()) continue;
            try {
              await fs.access(path.join(trajectoryDir, attempt.name, 'trajectory.json'));
              hasCanonicalTrajectory = true;
            } catch { /* No trajectory in this attempt. */ }
          }
        } catch { /* This run has no canonical trajectory directory. */ }
      }
    } catch { /* No runs directory. */ }
    if (!hasCanonicalTrajectory) continue;

    const definition = JSON.parse(await fs.readFile(path.join(issueDir, 'verify.case.json'), 'utf8'));
    const locations = definition['fault location'];
    const cause = definition['Root cause'];
    if (!Array.isArray(locations) || !locations.length || typeof cause !== 'string' || !cause.trim()) {
      throw new Error(`Incomplete GT definition: ${issueDir}`);
    }
    const repository = definition.issue.repository;
    const number = definition.issue.number;
    const issueUrl = definition.issue.url;
    if (!repository || !issueUrl || entry.name !== `issue_${number}`) {
      throw new Error(`Invalid issue identity: ${issueDir}`);
    }
    const locationText = locations.map((location) => {
      const line = location.line_start
        ? `:${location.line_start}${location.line_end && location.line_end !== location.line_start ? `-${location.line_end}` : ''}`
        : '';
      const fn = location.function ? ` (${location.function})` : '';
      return `${location.file}${line}${fn}`;
    }).join('\n');
    rows.push({
      agent: unit.name.replace(/^\d+-/, ''),
      repository,
      repositoryUrl: `https://github.com/${repository}`,
      number,
      issueUrl,
      locationText,
      cause,
    });
  }
}

rows.sort((a, b) => a.agent.localeCompare(b.agent) || a.number - b.number);
if (rows.length !== 56) throw new Error(`Expected 56 current GT issues, found ${rows.length}`);

const workbook = Workbook.create();
const sheet = workbook.worksheets.add('GT cases');
sheet.showGridLines = false;
sheet.getRange('A1:F1').values = [[
  'agent', 'agent repo', 'issue', 'issuelink', 'fault_location', 'root_cause',
]];
sheet.getRange(`A2:F${rows.length + 1}`).values = rows.map((r) => [
  r.agent, r.repository, r.number, r.issueUrl, r.locationText, r.cause,
]);
const last = rows.length + 1;
sheet.getRange(`A1:F${last}`).format.font = { name: 'Arial', size: 10, color: '#1F2937' };
sheet.getRange('A1:F1').format = {
  fill: '#1F3A5F',
  font: { name: 'Arial', size: 10, bold: true, color: '#FFFFFF' },
  rowHeight: 30,
};
sheet.getRange(`B2:B${last}`).format.font = { name: 'Arial', size: 10, color: '#1459A5' };
sheet.getRange(`D2:D${last}`).format.font = { name: 'Arial', size: 10, color: '#1459A5' };
sheet.getRange(`C2:C${last}`).setNumberFormat('0');
sheet.getRange(`E2:F${last}`).format.wrapText = true;
sheet.getRange(`A2:F${last}`).format.verticalAlignment = 'top';
for (const [column, width] of Object.entries({ A: 25, B: 39, C: 11, D: 64, E: 86, F: 112 })) {
  sheet.getRange(`${column}:${column}`).format.columnWidth = width;
}
for (let i = 0; i < rows.length; i++) {
  const r = rows[i];
  const height = Math.min(320, Math.max(34,
    Math.ceil(r.locationText.length / 84) * 15,
    Math.ceil(r.cause.length / 108) * 15));
  sheet.getRange(`A${i + 2}:F${i + 2}`).format.rowHeight = height;
}
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(2);
const table = sheet.tables.add(`A1:F${last}`, true, 'GroundTruthCases');
table.style = 'TableStyleMedium2';

workbook.recalculate();
const check = await workbook.inspect({ kind: 'table', range: 'GT cases!A1:F4',
  include: 'values,formulas', tableMaxRows: 4, tableMaxCols: 6, maxChars: 3000 });
console.log(check.ndjson);
const preview = await workbook.render({ sheetName: 'GT cases', range: 'A1:F4', scale: 1, format: 'png' });
await fs.writeFile(path.join(outputDir, 'preview.png'), new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, 'gt-56.xlsx'));
console.log(`Saved ${rows.length} rows to ${path.join(outputDir, 'gt-56.xlsx')}`);
