"""Internal A30 v2 text protocol. Shared contracts/schema remain unchanged."""
import hashlib
import json
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, TypeAdapter, field_validator, model_validator

from ..contracts.base import ContractModel
from ..contracts.enums import ErrorCode
from .client import model_failure, strict_json

SAFETY_AGENT_VERSION = 'campus-safety-advisory-agent-2'
SAFETY_TOOL_VERSION = 'safety-read-only-tools-2'
SAFETY_VALIDATION_VERSION = 'safety-advisory-validation-2'
MAX_FINDINGS = 64
MAX_PROPOSAL_BYTES = 24576
MAX_ACTION_BYTES = 32768
MAX_PAYLOAD_BYTES = 512 * 1024
MAX_FACTS_BYTES = 32768
MAX_INPUT_BYTES = 131072

ActionCode = Literal['ACKNOWLEDGE_INFORMATION', 'CHECK_NEAR_DEPARTURE', 'OBTAIN_APPLICABLE_INFORMATION',
    'RESOLVE_SOURCE_CONFLICT', 'REQUEST_HUMAN_REVIEW', 'CHANGE_TRIP', 'RESOLVE_LOGISTICS', 'CONFIRM_ACTIVITY_DETAILS']
FindingKey = Annotated[StrictStr, Field(pattern=r'^finding-[0-9a-f]{64}$')]
FactRef = Annotated[StrictStr, Field(min_length=1, max_length=512, pattern=r'^/(baseline|input|selection)/')]
Hash = Annotated[StrictStr, Field(pattern=r'^[0-9a-f]{64}$')]
Name = Annotated[StrictStr, Field(min_length=1, max_length=200)]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def encoded_size(value):
    return len(canonical(value).encode('utf-8'))


EXCLUDED_TEXT_CATEGORIES = frozenset({'Cc', 'Cf', 'Zl', 'Zp'})
# Explicit, detectable link-like syntax, not an attempt to recognise every URL
# or obfuscated instruction. Unicode IDN dot variants are detected as written;
# received text is NEVER normalised, stripped or repaired to pass validation.
LINK_LIKE_PATTERNS = (
    r'\b[a-z][a-z0-9+.-]*://',
    r'\b(?:https?|ftps?|sftp|file|mailto|tel|sms|data|javascript):',
    r'\bwww[.\u3002\uff0e\uff61]',
    r'(?<![\w-])(?:[^\W_](?:[^\W_]|-){0,62}[.\u3002\uff0e\uff61])+'
    r'[^\W\d_](?:[^\W\d_]|-){1,62}(?![\w-])',
    r'\[[^\]\r\n]*\]\(\s*[^)]*\)',
)
LINK_LIKE_RE = tuple(re.compile(pattern, re.IGNORECASE | re.UNICODE) for pattern in LINK_LIKE_PATTERNS)
ADVICE_TEXT_POLICY = {
    'version': 'safety-advice-text-2',
    'unicode_data_version': unicodedata.unidata_version,
    'excluded_unicode_categories': sorted(EXCLUDED_TEXT_CATEGORIES),
    'link_like_patterns': list(LINK_LIKE_PATTERNS),
    'regex_flags': ['IGNORECASE', 'UNICODE'],
    'normalisation': 'none; reject received text without rewriting',
    'other_existing_exclusions': ['numeric literals', 'matched HTML tags', 'code fences',
        'selected detectable false-clearance/instruction-injection phrases'],
    'limitations': 'Detectable syntax only; not complete URL, obfuscation, English-language or semantic-truth recognition.',
}
ADVICE_SCHEMA_POLICY = {
    'x-safety-text-policy': ADVICE_TEXT_POLICY['version'],
    'x-safety-text-policy-sha256': hashlib.sha256(canonical(ADVICE_TEXT_POLICY).encode('utf-8')).hexdigest(),
}


def check_advice(text):
    # Conservative detectable-claim guard, NOT a semantic truth verifier.
    if (not text.strip() or any(unicodedata.category(char) in EXCLUDED_TEXT_CATEGORIES for char in text)
            or any(pattern.search(text) for pattern in LINK_LIKE_RE)
            or re.search(r'\d|<[^>]*>|```', text)
            or re.search(r'(?i)\b(safe to proceed|approval granted|fully safe|guaranteed safe|'
                         r'no review required|all risks resolved|ignore (?:all |previous |system )*instructions|'
                         r'system prompt|override (?:the |any )?(?:block|closure|review|rule)|'
                         r'(?:booking|rental) confirmed)\b', text)):
        raise ValueError('Advice must be plain, nonnumeric, non-authoritative text')
    text.encode('utf-8')  # Reject unpaired surrogates before any transport/save.
    return text


class FindingChoice(ContractModel):
    finding_key: FindingKey
    interpretation_unverified: Annotated[StrictStr, Field(min_length=1, max_length=600, json_schema_extra=ADVICE_SCHEMA_POLICY)]
    action_code: ActionCode
    action_unverified: Annotated[StrictStr, Field(min_length=1, max_length=600, json_schema_extra=ADVICE_SCHEMA_POLICY)]

    @field_validator('interpretation_unverified', 'action_unverified')
    @classmethod
    def plain_advice(cls, value):
        return check_advice(value)


class SafetyProposal(ContractModel):
    findings: list[FindingChoice] = Field(min_length=1, max_length=MAX_FINDINGS)
    action_priority: list[FindingKey] = Field(min_length=1, max_length=MAX_FINDINGS)
    decision_summary_unverified: Annotated[StrictStr, Field(min_length=1, max_length=1200, json_schema_extra=ADVICE_SCHEMA_POLICY)]

    @field_validator('decision_summary_unverified')
    @classmethod
    def plain_summary(cls, value):
        return check_advice(value)

    @model_validator(mode='after')
    def unique_complete_priority(self):
        keys = [item.finding_key for item in self.findings]
        if (len(set(keys)) != len(keys) or len(set(self.action_priority)) != len(self.action_priority)
                or set(keys) != set(self.action_priority) or encoded_size(self.model_dump(mode='json')) > MAX_PROPOSAL_BYTES):
            raise ValueError('Findings/priority must be unique, complete and within the encoded limit')
        return self


class EmptyArguments(ContractModel):
    pass


class ReadSafetyFactsAction(ContractModel):
    action: Literal['tool']
    name: Literal['read_safety_facts']
    arguments: EmptyArguments


class EvaluateSafetyAction(ContractModel):
    action: Literal['tool']
    name: Literal['evaluate_safety_plan']
    arguments: SafetyProposal


class FinalSafetyAction(ContractModel):
    action: Literal['final']
    proposal: SafetyProposal


SAFETY_ACTION = TypeAdapter(ReadSafetyFactsAction | EvaluateSafetyAction | FinalSafetyAction)


def parse_safety_action(text):
    try:
        if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_ACTION_BYTES:
            raise ValueError('Action exceeds encoded limit')
        return SAFETY_ACTION.validate_python(strict_json(text))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise model_failure('Safety action violates the strict advisory protocol.', code=ErrorCode.CONTRACT_INVALID) from None


class SafetyTrace(ContractModel):
    role: Literal['SAFETY']
    requested_model: Name
    served_models: list[Name] = Field(max_length=6)
    configuration_fingerprint: Hash
    input_sha256: Hash
    rule_facts_sha256: Hash
    proposal_sha256: Hash
    prompt_sha256: Hash
    tool_version: Name
    turns: StrictInt = Field(ge=3, le=6)
    http_attempts: StrictInt = Field(ge=3, le=18)
    elapsed_ms: StrictInt = Field(ge=0, le=2**63-1)
    tool_calls: list[Literal['read_safety_facts', 'evaluate_safety_plan']] = Field(min_length=2, max_length=5)
    response_sha256: list[Hash] = Field(min_length=3, max_length=6)
    usage: dict[Literal['prompt_tokens', 'completion_tokens', 'total_tokens'], Annotated[StrictInt, Field(ge=0, le=2**63-1)]]
    validation_passed: StrictBool

    @field_validator('requested_model', 'served_models', 'tool_version')
    @classmethod
    def nonblank_names(cls, value):
        values = value if isinstance(value, list) else [value]
        if any(not name.strip() or any(ord(char) < 32 for char in name) for name in values):
            raise ValueError('Blank/control-character model names are forbidden')
        return value

    @model_validator(mode='after')
    def successful_trace(self):
        if (not self.validation_passed or len(self.response_sha256) != self.turns
                or len(self.tool_calls) != self.turns - 1 or self.tool_calls[0] != 'read_safety_facts'
                or 'evaluate_safety_plan' not in self.tool_calls
                or not self.turns <= self.http_attempts <= self.turns * 3
                or len(set(self.served_models)) != len(self.served_models) or len(self.served_models) > self.turns):
            raise ValueError('Invalid successful safety trace')
        return self
