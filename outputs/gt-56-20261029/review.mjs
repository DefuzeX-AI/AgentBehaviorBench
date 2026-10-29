import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const dir = path.dirname(fileURLToPath(import.meta.url));
const workbook = await SpreadsheetFile.importXlsx(
  await FileBlob.load(path.join(dir, 'gt-57.xlsx')),
);
const summary = await workbook.inspect({
  kind: 'table', range: 'GT cases!A1:F4', include: 'values,formulas',
  tableMaxRows: 4, tableMaxCols: 6, maxChars: 1000,
});
console.log(summary.ndjson);
const image = await workbook.render({ sheetName: 'GT cases', range: 'A1:F3', scale: 1, format: 'png' });
await fs.writeFile(path.join(dir, 'gt-57-preview.png'), new Uint8Array(await image.arrayBuffer()));
