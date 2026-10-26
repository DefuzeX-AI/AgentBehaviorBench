# Official executable provenance

- Upstream: https://github.com/GCWing/OpenBitFun
- Official release: https://github.com/GCWing/OpenBitFun/releases/tag/v1.0.7
- Matching source revision: `db7d36544896c62bc53c48c8774bcb13d4aa5e49`
- Package-based `[source] method="install"` materializes the checked-in release descriptor under `install/abb-native-release.json`. The installer downloads the declared archive, verifies SHA-256 of the whole archive, and extracts the original `openbitfun` executable. It does not compile a custom fork.
- AMD64 archive SHA256: `7c505bdc99a86d7d554aa0d8a177ca8c9ee144bb88c1cbd4abf65603b3ca6797`
- ARM64 archive SHA256: `70d2ba0023722f705692fcc15dda27587c1f89011b803c92b36c3dd7e622eaf0`
- Native ACP command: `openbitfun acp serve` (stdio). Docker verification confirmed `openbitfun acp doctor` reports ready after GlobalConfig receives one enabled OpenAI-compatible model.
- ABB's outer launcher only configures model/state/workspace via `ABB_AGENT_MODEL_*`, then execs the official binary. Prompts, tools, permissions and model loop remain upstream.
