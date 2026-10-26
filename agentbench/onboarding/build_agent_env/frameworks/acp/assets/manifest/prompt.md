# Derive ACP manifest facts

Return facts matching this schema from supplied source evidence. Select the native
ACP stdio command as argv, absolute container cwd, optional string input_key,
permission_policy, and optional advertised auth_method. Missing optional values
are null. Return framework="acp". Do not emit TOML, a Python binding, graph config,
or an in_process adapter. Identity, launch, source metadata and SDK settings are
assembled by BBA. Include no credentials or guessed command switches.

Follow framework_requirements.acp. Native observation preserves the actual CLI's
requests; do not enable proxy replacement. Ordinary configurable Agents OMIT facts.model:
absence means shared selection, OpenRouter -> DeepSeek -> GLM. Do not emit source="shared"
or repeated setup comments. The verified outer launcher must already consume
ABB_AGENT_MODEL_API_KEY, ABB_AGENT_MODEL_BASE_URL, ABB_AGENT_MODEL and
ABB_AGENT_MODEL_PROVIDER and map them to the native CLI. Set models=[]; do not list
internal ABB_AGENT_MODEL_* variables as runtime inputs. Only add model.metadata_paths
if evidence demonstrates GET <selected-base>/models. Preserve tool_routes.
If a configurable Agent lacks that launcher, return needs_input identifying the
missing outer integration rather than pinning a provider or inventing a launcher.
An explicit model.provider pins the selected provider and wins over global selection.
For provider/protocol/tool-constrained native integrations, declare model.provider,
source="native" and reason. If source evidence proves that the native client can
consume runtime-selected OpenAI Chat Completions base/model/credential settings,
model.runtime_configurable=true opts into that contract while retaining native
provider/model constraints. Set models=[] and use the ABB_AGENT_MODEL_* launcher
contract; do not declare static credentials/routes or runtime-owned inputs. This
capability does not support Responses, Messages or provider-owned tool services.
Other native integrations retain dedicated configuration; declare native credentials in
models.agent_env so BBA retains them as runtime secrets. Never invent a dummy key or assume a model API key also
authenticates the CLI's vendor login. Only
list tool_routes supported by source evidence. Runtime env_keys declare required
nonsecret CLI configuration. Native text input normally has input_fields=[];
structured input_key must match a declared string field. Unknown authentication,
installation or endpoint requirements need a needs_input response with concrete
questions. Cite exact context.files paths, not external filenames you have not read.
