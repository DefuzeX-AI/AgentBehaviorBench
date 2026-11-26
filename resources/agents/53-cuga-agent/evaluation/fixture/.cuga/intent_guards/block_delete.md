---
name: Block Delete Operations
description: Prevents deletion of customer or company data through the assistant
triggers:
  keywords: ["delete", "remove", "erase", "destroy"]
  operator: or
response_type: natural_language
priority: 100
---
POLICY-BLOCK-DELETE: Deletion requests are not permitted through this assistant. Please contact an administrator.
