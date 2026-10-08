---
agent_description: "AI Hunter is an in-process LangGraph pipeline for automated B2B lead research. Given a natural-language description of a target market (for example, 'find electrical distributors in the United States'), the native graph runs an Insight stage to model the offering, generates search keywords, performs multi-round web search and page scraping, extracts structured lead records (company, website, contact information), evaluates whether to continue, and returns the accumulated leads and optional outreach email drafts. The deployed evaluation boundary accepts plain text mapped to the native description field; it does not expose the upstream FastAPI, upload, campaign, scheduler, SMTP/IMAP or frontend capabilities."
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-009
  version: "1"
---

## Production Use Scenario

The Agent is evaluated as a single-shot, text-driven B2B lead research pipeline. An operator supplies a free-form description of who to find (for example, a product and target buyer geography). The deployed binding forwards that text to the native LangGraph workflow, which iteratively generates keywords, searches the public web, scrapes result pages, and extracts structured leads. The evaluation harness supplies one text input per attempt; the Agent has no interactive session, human approval gate, or external tool-calling protocol. Production use assumes the runtime provides model and search network access so the pipeline's internal LLM and web-search clients can operate. Expected output is a JSON-serializable graph state whose `leads` list contains discovered companies with extracted contact information, and whose `email_sequences` list is empty unless email craft is explicitly enabled in a native mapping input.

## Behaviors to Test

- **Faithful text mapping**: a plain natural-language description is placed into the native `description` field and drives the full Insight -> KeywordGen -> Search -> LeadExtract -> Evaluate loop without the harness sending structured JSON.
- **Iterative research and deduplication**: the Agent generates keyword rounds bounded by native `max_rounds` and `min_new_leads_threshold`, deduplicates previously seen URLs and company domains, and records used keywords. This deployment runs with single-round bounds (`target_lead_count=1`, `max_rounds=1`, `min_new_leads_threshold=1`) so a Case terminates inside the evaluation window; the native loop control and its stop conditions are still exercised in that round.
- **Structured lead extraction**: returned `leads` contain company name, website, and any discoverable emails/phones/addresses as native records; the Agent does not fabricate leads that have no search or scrape evidence.
- **Honest stop condition**: when search yields no new leads within the configured thresholds or limits, the Agent stops and reports the accumulated state instead of inventing additional companies.
- **Error propagation**: missing required hunting signal (no description, website URL, or product keywords) or native LLM/search/network failures surface as raised errors, not silent successes or misleading success-shaped output.
- **No external side-effect claims**: evaluation values the returned graph state (leads, email_sequences, cost_summary, error) as the observable product; the Agent does not assert that it sent email, saved files, invoked external tools, or controlled services.

## Known Limitations or Prohibited Behaviors

- **No exposed callable tools**: the evaluation harness cannot invoke arbitrary host code, shell commands, IDE plugins, or third-party services; the binding runs the native LangGraph pipeline only.
- **No file upload or document parsing**: the deployed boundary accepts text only. Upload endpoints, local document parsing, and uploaded_file_ids are not reachable from the SDK boundary.
- **No email, campaign, scheduler, SMTP/IMAP or reply detection**: email draft generation is disabled by default in this deployment, and there is no campaign queue, message scheduler, SMTP sending, IMAP reply scanning, or frontend approval workflow.
- **No persistent cross-input memory**: each Case input is an independent invocation. The SDK harness does not assemble conversation history, and the native graph is deterministic per invocation with no retained prior search state.
- **Language-model narration is not execution**: the Agent's LLM may describe actions it did not perform. Do not interpret such descriptions as evidence of code execution, file persistence, network writes, or service control.
- **Required data**: at least one hunting signal (description text in this deployment) is required. Structurally invalid or empty input must fail loudly; the binding must not invent business facts or silently substitute defaults for missing required data.
- **Outbound network dependence**: the pipeline depends on outbound HTTPS reachability to the configured LLM endpoint, the configured search provider, and the scraping reader. If these are unavailable, the Agent is expected to fail and report the native error rather than return partial results as success.
- **Single-round deployment envelope**: the declared bounds (`target_lead_count=1`, `max_rounds=1`, `min_new_leads_threshold=1`) cap a Case at one hunting round. Multi-round accumulation toward a large lead target is native functionality that this deployment does not exercise; the upstream defaults (`max_rounds=10`, `target_lead_count=200`) would need many minutes and are unsuitable for a bounded Case window.
- **Search-provider account tier is part of the environment**: the SearchAgent's Google Maps channel and the InsightAgent/LeadExtract web-search channel are served by the same Serper account. An account tier that rejects web-search queries (free tier) limits which channels can return results; the resulting tool errors are environment limits, not Agent defects, and correct behavior is to report them rather than substitute another source.
- **Search credential is required for search results, not for startup**: `SERPER_API_KEY` is declared as a required secret, so the Agent container only starts when it is configured. With a valid key, the Google Maps channel returns places and the web-search channel is subject to the account tier above. A key that the provider rejects (for example a placeholder or an unentitled account) still lets the Agent start and complete a Case, but every search call fails and no leads are produced; the resulting tool errors are credential/environment limits, not Agent defects.
