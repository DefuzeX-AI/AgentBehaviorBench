# Derive ACP manifest facts

Return facts matching this schema from supplied source evidence. Select the native
ACP stdio command as argv, absolute container cwd, optional string input_key,
permission_policy, and optional advertised auth_method. Missing optional values
are null. Return framework="acp". Do not emit TOML, a Python binding, graph config,
or an in_process adapter. Identity, launch, source metadata and SDK settings are
assembled by BBA. Include no credentials or guessed command switches.

Follow framework_requirements.acp. Native observation preserves the actual CLI's
model, endpoint and authentication; do not configure an OpenRouter replacement.
Declare native model credential variable names in models.agent_env so BBA retains
them as runtime secrets. Never invent a dummy key or assume a model API key also
authenticates the CLI's vendor login. Only
list tool_routes supported by source evidence. Runtime env_keys declare required
nonsecret CLI configuration. Native text input normally has input_fields=[];
structured input_key must match a declared string field. Unknown authentication,
installation or endpoint requirements need a needs_input response with concrete
questions. Cite exact context.files paths, not external filenames you have not read.
