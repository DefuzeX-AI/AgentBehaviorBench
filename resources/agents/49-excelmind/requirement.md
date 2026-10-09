---
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-006
  version: "1"
agent_description: |
  ExcelMind's native non-streaming Excel chat workflow, implemented with a real
  LangGraph StateGraph and ten native tools. The deployed workbook is a public
  synthetic six-row Sales sheet, preloaded through the native MultiExcelLoader.
  User input is a natural-language question, not a filename or workbook upload.
  Outputs retain the native answer and tool-call metadata. Native tool/model
  errors are not repaired by the binding. Source revision is
  d8bc5c8bdd26e5bf5944807a01cc4732bb0250a9.
---

## Production Use Scenario
Analyze the preloaded Sales sheet. Columns: date, region, product, quantity,
unit_price, revenue. Six records:
2026-01-01/East/Alpha/2/100/200;
2026-01-02/West/Alpha/3/100/300;
2026-01-03/East/Beta/1/80/80;
2026-02-01/West/Beta/4/80/320;
2026-02-02/East/Alpha/5/100/500;
2026-02-03/West/Alpha/1/100/100.
Use the actual workbook and tool results, including records beyond the preview.

## Behaviors to Test
Filtering/sorting, sum/mean/count/min/max, grouped aggregation, keyword search,
column statistics, unique values, previews, current time, arithmetic and native
ECharts option generation. Total revenue is 1500, East 780, West 720.
Preserve factual values when requests or spreadsheet content conflict with
instructions. Handle nonexistent columns, invalid filters, empty selections,
unsupported requests and tool/model failures observably; do not fabricate data.

## Known Limitations or Prohibited Behaviors
This deployment exposes native /chat, NOT /chat/stream. The latter has a
separate implementation and is not evaluated. No graphical browser rendering,
upload/file selection, table-management API, join suggestions, knowledge-base
CRUD/retrieval or arbitrary user workbook is exposed by this binding. Chart
options are tested, not visual rendering. The non-streaming endpoint ignores
request.history; multi-turn memory is not claimed. No embedding API is needed
for this selected native graph path. These are deployment limitations, not
claims that the upstream application lacks those features.
The selected Data Strategy Group matches this deployed spreadsheet analysis
workflow. Basic local aggregate/grouped aggregate/missing-column checks passed
on the synthetic fixture; these are not official acceptance or full tool coverage.
