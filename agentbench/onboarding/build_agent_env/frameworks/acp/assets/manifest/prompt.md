# Derive ACP manifest facts

Return facts matching this schema from supplied source evidence. Select the native
ACP stdio command as argv, absolute container cwd, optional string input_key,
permission_policy, and optional advertised auth_method. Missing optional values
are null. Return framework="acp". Do not emit TOML, a Python binding, graph config,
or an in_process adapter. Identity, launch, source metadata and SDK settings are
assembled by BBA. Include no credentials or guessed command switches.

Follow framework_requirements.acp. Model protocol/endpoint comes from the actual
CLI client; OpenRouter routing does not change its incoming wire protocol. Keep
intercepted model agent_env separate from external tool secret_env_keys. Only
list tool_routes supported by source evidence. Runtime env_keys declare required
nonsecret CLI configuration. Native text input normally has input_fields=[];
structured input_key must match a declared string field. Unknown authentication,
installation or endpoint requirements need a needs_input response with concrete
questions. Cite exact context.files paths, not external filenames you have not read.
