# Official executable and reference-source provenance

- Upstream: https://github.com/microclaw/microclaw
- Official release: https://github.com/microclaw/microclaw/releases/tag/v0.10.1
- Matching source tag commit: `45ad5e7a8c705080a94543c92319f81b7e0e884f`.
- Package-based `[source] method="install"` materializes only the checked-in release descriptor. The installer consumes the declared release, checks the whole archive and writes its original regular executable. It does not compile a custom fork.
- ARM64 archive SHA256: `35c4e44432e313877da15e8ac51c34464194ec39583c73be6be158c44d2e350d`.
- AMD64 archive SHA256: `61211b004a34979db7fb07c508b7f789db997086e09140954c678245ca45b61f`.
- Both official default-feature asset URLs/hashes and source revision are stored in `install/abb-native-release.json`. This is not a claim of locally bit-reproducible compilation.
- The corresponding724-entry Git tree, including its original directory symlink, was separately acquired and verified for source review. It is not flattened, modified, committed or substituted into a fake source acquisition path. The normal build uses the release package, not that reference tree.
- Ubuntu24.04 matches the official Linux GNU build environment. The native command is `microclaw acp`.
- ABB's outer launcher only configures model/state/workspace/logging, then execs the official executable. Native config/channel validation, prompts, tools, guardrails, model loop and responses remain unchanged.
- Source references: `src/main.rs`, `src/acp.rs`, `crates/microclaw-engine/src/config/core.rs`, `crates/microclaw-engine/src/config/llm_profiles.rs` and `crates/microclaw-engine/src/llm/openai.rs`.
