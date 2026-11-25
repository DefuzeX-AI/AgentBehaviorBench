# Native execution and onboarding

Use `agentbench agent add REPOSITORY -b --sdk native` to generate integration
files with an offline, text-input profile contract. This requires the configured
onboarding model but no KUMA installation, credential, or strategy catalog.
The native profile describes the real agent, its deployment and limitations;
it does not claim behavioral certification. The independent `local` SDK's
onboarding capabilities are unchanged.

Supply an `abb.cases.v1` case file to `agentbench evaluate AGENT --sdk native
--case-file FILE --cases 1 --max-steps 1 --no-view -y` for a single-turn run.
Review execution status, recorded model traffic and trajectory completeness
separately. Imported inputs are checked against the executed inputs.
