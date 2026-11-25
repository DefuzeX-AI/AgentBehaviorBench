---
agent_description: |
  OASIS native source-security scanner with real local embeddings and reports.
input_type: text
---

## Production Use Scenario

The smoke deployment creates a real local Python greeting program containing the
supplied text and invokes the original scanner. Native source indexing, CPU Ollama
embeddings, model analysis, validation and report generation are preserved.

## Behaviors to Test

Return real native JSON reports. Never fabricate vulnerabilities or scan results.
No external scan target is used. The source fixture and reports remain in the
case workspace. Model chat calls use the shared runtime replacement endpoint.
The smoke scan uses the native zero similarity threshold so the short greeting
program reaches model analysis even when retrieval similarity is low. Native
vulnerability definitions are loaded from the original source directory.

## Limitations

This checks native scan mode, not authenticated dashboard interaction.
