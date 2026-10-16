"""Exportable internal v1 component contract, independent of shared schema 1.0."""
from .safety_identity import SafetyIdentitySeed, SAFETY_SYSTEM_PROMPT
from .safety_schema import (SAFETY_ACTION, SAFETY_AGENT_VERSION, SAFETY_TOOL_VERSION, SAFETY_VALIDATION_VERSION,
    SafetyProposal, SafetyTrace, MAX_ACTION_BYTES, MAX_FACTS_BYTES, MAX_FINDINGS,
    MAX_INPUT_BYTES, MAX_PAYLOAD_BYTES, MAX_PROPOSAL_BYTES, canonical)
from .safety_tools import FindingDefinition, ValidatedSafetyPlan
from .coordinator import digest


def safety_contract_document():
    return {
        'status':'B_COMPONENT_IMPLEMENTED_A_B_FREEZE_AND_PRODUCTION_WIRING_PENDING',
        'shared_schema_version':'1.0',
        'agent_version':SAFETY_AGENT_VERSION,'tool_version':SAFETY_TOOL_VERSION,
        'validation_version':SAFETY_VALIDATION_VERSION,
        'prompt_sha256':digest(SAFETY_SYSTEM_PROMPT+canonical(SAFETY_ACTION.json_schema())),
        'encoded_utf8_limits':{'input':MAX_INPUT_BYTES,'read_facts':MAX_FACTS_BYTES,'proposal':MAX_PROPOSAL_BYTES,
            'action':MAX_ACTION_BYTES,'complete_audit_payload':MAX_PAYLOAD_BYTES,'client_request':131072,
            'client_response':262144},
        'semantic_limits':{'findings':MAX_FINDINGS,'catalog_entries':512,'fact_refs_per_finding':32,
            'baseline_evidence':128,'source_refs':128,'turns_min':3,'turns_max':6,'attempts_per_turn_max':3},
        'notes':[
            'Schemas and versioned pure validators are both required; JSON schema alone is insufficient.',
            'All encoded limits apply together; individual field maxima are not an unlimited cross product.',
            'Advice rejects numeric literals, control characters, markup/URLs and selected detectable false-clearance/injection phrases.',
            'English instructions and human review remain necessary; schema cannot prove natural-language truth.',
            'Proposal findings order is preserved; priority is a separate complete permutation.',
            'Source/fact references are added by tools, never accepted in model proposals.',
            'No model safety flag, production migration, audit save port, factory, Hybrid or Orchestrator wiring is enabled by this component.'
        ],
        'schemas':{'action':SAFETY_ACTION.json_schema(),'proposal':SafetyProposal.model_json_schema(),
            'validated_plan':ValidatedSafetyPlan.model_json_schema(),'trace':SafetyTrace.model_json_schema(),
            'finding_definition':FindingDefinition.model_json_schema(),'identity_seed':SafetyIdentitySeed.model_json_schema()}}
