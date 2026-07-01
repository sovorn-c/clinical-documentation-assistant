"""CodeSuggestion -> FHIR Condition/Claim mapping (execute-plan §8 point 4).

Net-new: map an approved ``CodeSuggestion`` list to FHIR ``Condition`` (and
optionally ``Claim``) resources. M1's ``FhirExporter`` only emits the note
``DocumentReference``; nothing upstream produces diagnosis/claim resources.

Versioning (Phase 0 Decision A): the note ``DocumentReference`` is R5 (M1,
reused as-is); the net-new diagnosis resources are R4-lineage. ``fhir.resources``
8.x exposes R4 as the ``R4B`` subpackage (R4 + errata; identical structure to
R4 for Condition/Claim) and R5 as the top-level default (which M1 uses). So we
build Conditions/Claims with ``fhir.resources.R4B`` classes — construction
validates against the R4 schema, satisfying the Phase 4 acceptance
("exports validate").

S3 outputs ICD-10-CM codes, so ``code.system`` is the ICD-10-CM OID. ``Claim``
needs billing context (insurance + priority) that the clinical-documentation
demo doesn't have; ``codes_to_claim`` therefore requires that context
explicitly rather than fabricating payer data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from auto_medical_coder import CodeSuggestion

_ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"
_CLINICAL_ACTIVE = "http://terminology.hl7.org/CodeSystem/condition-clinical"
_CLAIM_TYPE = "http://terminology.hl7.org/CodeSystem/claim-type"
_CLAIM_PRIORITY = "http://terminology.hl7.org/CodeSystem/processpriority"


def _slug(code: str) -> str:
    return code.replace(".", "-").replace(" ", "-").lower()


def codes_to_conditions(
    suggestions: list[CodeSuggestion] | list[dict[str, Any]],
    *,
    patient_ref: str,
    encounter_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Map approved CodeSuggestions to validated FHIR R4B ``Condition`` resources.

    Returns a list of resource dicts (``model_dump(mode="json")``). Each
    Condition carries the ICD-10-CM code, an active clinicalStatus, and
    references to the patient (and encounter, if given). Construction goes
    through ``fhir.resources.R4B.Condition``, which validates the schema.
    """
    from fhir.resources.R4B.condition import Condition

    out: list[dict[str, Any]] = []
    for s in suggestions:
        code = _field(s, "code")
        if not code:
            continue
        description = _field(s, "description")
        body: dict[str, Any] = {
            "id": f"cond-{encounter_ref or patient_ref}-{_slug(code)}",
            "clinicalStatus": {"coding": [{"system": _CLINICAL_ACTIVE, "code": "active"}]},
            "code": {
                "coding": [
                    {
                        "system": _ICD10CM,
                        "code": code,
                        **({"display": description} if description else {}),
                    }
                ]
            },
            "subject": {"reference": f"Patient/{patient_ref}"},
        }
        if encounter_ref:
            body["encounter"] = {"reference": f"Encounter/{encounter_ref}"}
        # Construction validates against the R4B schema — raises on a bad shape.
        cond = Condition(**body)
        out.append(cond.model_dump(mode="json"))
    return out


def codes_to_claim(
    suggestions: list[CodeSuggestion] | list[dict[str, Any]],
    *,
    patient_ref: str,
    provider_ref: str,
    coverage_ref: str,
    priority: str = "normal",
    encounter_ref: str | None = None,
) -> dict[str, Any]:
    """Build a single FHIR R4B ``Claim`` referencing one Condition per code.

    Unlike ``codes_to_conditions``, this requires billing context (provider,
    coverage, priority) which the clinical-documentation demo does not carry —
    so ``export_fhir`` does not call it by default. Provide the context to
    produce a validated Claim (e.g. for a billing integration).
    """
    from fhir.resources.R4B.claim import Claim

    if not suggestions:
        raise ValueError("at least one CodeSuggestion is required for a Claim")

    conditions = codes_to_conditions(
        suggestions, patient_ref=patient_ref, encounter_ref=encounter_ref
    )
    diagnosis = [
        {"sequence": i + 1, "diagnosisReference": {"reference": f"Condition/{c['id']}"}}
        for i, c in enumerate(conditions)
    ]
    body: dict[str, Any] = {
        "id": f"claim-{encounter_ref or patient_ref}",
        "status": "active",
        "type": {"coding": [{"system": _CLAIM_TYPE, "code": "institutional"}]},
        "use": "claim",
        "patient": {"reference": f"Patient/{patient_ref}"},
        "provider": {"reference": provider_ref},
        "priority": {"coding": [{"system": _CLAIM_PRIORITY, "code": priority}]},
        "insurance": [{"sequence": 1, "focal": True, "coverage": {"reference": coverage_ref}}],
        "diagnosis": diagnosis,
        "created": datetime.now(UTC).isoformat(),
    }
    # Construction validates against the R4B schema.
    return Claim(**body).model_dump(mode="json")


def _field(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
