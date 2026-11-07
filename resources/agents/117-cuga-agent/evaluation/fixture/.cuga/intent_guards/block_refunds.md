---
id: block_refunds
name: Block Refund Operations
description: Refunds and payouts must go through the finance team, not the assistant
triggers:
  keywords: ["refund", "chargeback", "payout", "wire transfer"]
  operator: or
response_type: natural_language
priority: 100
---
POLICY-BLOCK-REFUND: Refund and payout requests are not handled by this assistant. Please contact the finance team.
