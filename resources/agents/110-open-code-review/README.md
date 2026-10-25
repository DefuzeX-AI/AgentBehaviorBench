# Slot 104: open-code-review (alibaba/open-code-review)

## Upstream Metadata
- **Repository**: https://github.com/alibaba/open-code-review
- **Commit**: `375f64cd6f67a48a135da83cfcf59c52669a09cb`
- **License**: Apache-2.0
- **Framework**: acp (Native Dual-Binary Go ACP Adapter)

## Architecture Overview
The container packages both the `opencodereview` CLI binary and the `ocr-acp` ACP adapter binary built from the official `acp/` module.
`bootstrap/launch.py` binds ABB intercepted runtime parameters to `OCR_LLM_*` variables and launches `ocr-acp --ocr-binary /opt/agent/bin/opencodereview`.
