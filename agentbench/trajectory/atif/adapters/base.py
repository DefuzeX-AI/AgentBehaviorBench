"""Source-specific boundary recognition; shared graph code validates ownership."""
from typing import Protocol
from ..contracts import EvidenceBundle, DelegationEvidence


class DelegationAdapter(Protocol):
    def identify(self, evidence: EvidenceBundle) -> DelegationEvidence: ...
