---
id: block_ssn
name: Block SSN Requests
description: Blocks requests involving Social Security Numbers (SSN)
triggers:
  keywords: ["ssn"]
  operator: or
response_type: natural_language
priority: 100
---
POLICY-BLOCK-SSN: Requests involving Social Security Numbers are not permitted.
