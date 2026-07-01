"""clin_core_glue — B1's net-new wiring (execute-plan §8).

The four points not covered by M1/S2/S3/S1 live here as small, testable
modules. Engine types are imported lazily (TYPE_CHECKING / inside function
bodies) so this package stays lightweight and does NOT force the heavy
upstream installs (torch / chromadb / spaCy model) on its own — the backend
pulls those.

Modules (filled in their phases):
  soap_text   — SOAPNote -> flat text, ahead of suggest-codes  (Phase 2, §8.2)
  deid        — de-id boundary helper for cloud-LLM calls      (Phase 2, §8.1)
  referral    — referral letter generation via LLMClient        (Phase 2, §8.3)
  fhir_codes  — CodeSuggestion -> FHIR Condition/Claim          (Phase 4, §8.4)
"""

from clin_core_glue.deid import redact_for_cloud
from clin_core_glue.fhir_codes import codes_to_conditions
from clin_core_glue.referral import generate_referral
from clin_core_glue.soap_text import flatten_soap

__all__ = [
  "flatten_soap",
  "redact_for_cloud",
  "generate_referral",
  "codes_to_conditions",
]
__version__ = "0.1.0"
