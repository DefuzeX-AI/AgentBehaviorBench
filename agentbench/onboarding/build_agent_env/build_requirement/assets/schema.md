Generate ONLY evaluation/input-schema.json, a local JSON Schema for the exact
Case payload the saved adapter/bindings accept. Derive required fields and types
from actual Agent input state. Do not describe output as input. Preserve required
structured fields; do not silently reduce structured input to a text prompt.
Only internal # references are permitted. No external URLs/files for $ref.
Follow sdk_requirements. The requirement document will reference this saved file
in the next step. Do not return requirement.md or any other file now.
