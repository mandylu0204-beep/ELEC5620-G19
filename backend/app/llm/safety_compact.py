"""Offline v4 candidate: lossless fact references and bounded single advice."""
from copy import deepcopy
from typing import Annotated, Literal
from pydantic import Field, StrictStr, TypeAdapter, field_validator, model_validator
from ..contracts.base import ContractModel
from ..contracts.dto import Provenance, SourceRef
from ..contracts.enums import ErrorCode
from .client import model_failure, strict_json
from .coordinator import digest
from .safety_schema import (ActionCode, Hash, MAX_FINDINGS, SafetyProposal,
    ReadSafetyFactsAction, ADVICE_SCHEMA_POLICY, canonical, check_advice, encoded_size)
from .safety_tools import ValidatedSafetyPlan
from .safety_diagnostics import proposal_failure
from .safety_v3 import SafetyToolset as V3Tools

CODEC_VERSION = 'safety-lossless-facts-1'
MAX_COMPACT_PROPOSAL_BYTES = 16384
MAX_COMPACT_ACTION_BYTES = 18432
ShortKey = Annotated[StrictStr, Field(pattern=r'^f(?:[0-9]|[1-5][0-9]|6[0-3])$')]


class CompactFinding(ContractModel):
    id: ShortKey
    action: ActionCode
    advice: Annotated[StrictStr, Field(min_length=1,max_length=96,
        json_schema_extra={**ADVICE_SCHEMA_POLICY,'x-max-words':12})]

    @field_validator('advice')
    @classmethod
    def bounded_advice(cls,value):
        check_advice(value)
        if len(value.split()) > 12:
            raise ValueError('At most twelve words; never truncate or repair')
        return value


class CompactProposal(ContractModel):
    facts_sha256: Hash
    findings: list[CompactFinding] = Field(min_length=1,max_length=MAX_FINDINGS)
    priority: list[ShortKey] = Field(min_length=1,max_length=MAX_FINDINGS)
    summary: Annotated[StrictStr, Field(min_length=1,max_length=160,
        json_schema_extra={**ADVICE_SCHEMA_POLICY,'x-max-words':24})]

    @field_validator('summary')
    @classmethod
    def bounded_summary(cls,value):
        check_advice(value)
        if len(value.split()) > 24:
            raise ValueError('At most twenty-four words')
        return value

    @model_validator(mode='after')
    def exact_priority_and_size(self):
        keys = [item.id for item in self.findings]
        if (len(set(keys)) != len(keys) or len(set(self.priority)) != len(self.priority)
                or set(keys) != set(self.priority)
                or encoded_size(self.model_dump(mode='json')) > MAX_COMPACT_PROPOSAL_BYTES):
            raise ValueError('Unique complete priority and encoded size required')
        return self


class EvaluateCompactAction(ContractModel):
    action: Literal['tool']
    name: Literal['evaluate_safety_plan']
    arguments: CompactProposal


class FinalCompactAction(ContractModel):
    action: Literal['final']
    proposal: CompactProposal


COMPACT_ACTION = TypeAdapter(ReadSafetyFactsAction | EvaluateCompactAction | FinalCompactAction)


def parse_compact_action(text):
    try:
        if not isinstance(text,str) or len(text.encode('utf-8')) > MAX_COMPACT_ACTION_BYTES:
            raise ValueError('Oversize compact action')
        return COMPACT_ACTION.validate_python(strict_json(text))
    except (ValueError,TypeError,RecursionError,UnicodeError):
        raise model_failure('Invalid compact safety action; no repair or fallback.',
            code=ErrorCode.CONTRACT_INVALID) from None


class ReferenceCodec:
    """Only canonical SourceRef/Provenance interned; reserved tags are escaped."""
    TAGS = frozenset({'$source','$provenance','$object'})

    def __init__(self):
        self.sources,self.provenances = [],[]
        self._sources,self._provenances = {},{}

    @staticmethod
    def _matches(value,model):
        if set(value) != set(model.model_fields):
            return False
        try:
            return canonical(model.model_validate(value).model_dump(mode='json')) == canonical(value)
        except (ValueError,TypeError):
            return False

    def encode(self,value):
        if isinstance(value,list):
            return [self.encode(item) for item in value]
        if not isinstance(value,dict):
            return deepcopy(value)
        if self._matches(value,SourceRef):
            key = canonical(value)
            if key not in self._sources:
                self._sources[key] = len(self.sources)
                self.sources.append({name:self.encode(item) for name,item in value.items()})
            return {'$source':self._sources[key]}
        if self._matches(value,Provenance):
            key = canonical(value)
            if key not in self._provenances:
                self._provenances[key] = len(self.provenances)
                self.provenances.append(deepcopy(value))
            return {'$provenance':self._provenances[key]}
        if self.TAGS.intersection(value):
            return {'$object':[[key,self.encode(item)] for key,item in value.items()]}
        return {key:self.encode(item) for key,item in value.items()}

    @classmethod
    def decode(cls,value,sources,provenances):
        def index(raw,table):
            if type(raw) is not int or not 0 <= raw < len(table):
                raise ValueError('Invalid reference index')
            return deepcopy(table[raw])
        if isinstance(value,list):
            return [cls.decode(item,sources,provenances) for item in value]
        if not isinstance(value,dict):
            return deepcopy(value)
        if set(value) == {'$source'}:
            return cls.decode(index(value['$source'],sources),[],provenances)
        if set(value) == {'$provenance'}:
            return index(value['$provenance'],provenances)
        if set(value) == {'$object'}:
            pairs = value['$object']
            if (not isinstance(pairs,list) or any(not isinstance(p,list) or len(p)!=2
                    or not isinstance(p[0],str) for p in pairs)
                    or len({p[0] for p in pairs}) != len(pairs)):
                raise ValueError('Invalid escaped object')
            return {key:cls.decode(item,sources,provenances) for key,item in pairs}
        return {key:cls.decode(item,sources,provenances) for key,item in value.items()}


class CompactSafetyToolset(V3Tools):
    """Every finding/fact retained; full keys and pointers stay host-bound."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        original = super().read_safety_facts()
        self._full_keys = {f'f{i}':item['finding_key'] for i,item in enumerate(original['findings'])}
        self._short_keys = {value:key for key,value in self._full_keys.items()}
        paths = {f'r{i}':path for i,path in enumerate(original['fact_catalog'])}
        refs = {value:key for key,value in paths.items()}
        codec = ReferenceCodec()
        wire = {key:codec.encode(value) for key,value in original.items()
            if key not in {'findings','fact_catalog'}}
        wire['findings'] = [{'id':self._short_keys[item['finding_key']],
            'category':item['category'],'campsite_id':item['campsite_id'],
            'facts':[refs[path] for path in item['fact_refs']],'actions':item['allowed_actions']}
            for item in original['findings']]
        wire.update(codec=CODEC_VERSION,facts_sha256=digest(canonical(original)),
            facts={alias:[path,codec.encode(original['fact_catalog'][path])] for alias,path in paths.items()},
            sources=codec.sources,provenances=codec.provenances)
        if canonical(self._expand_wire(wire)) != canonical(original):
            raise model_failure('Compact facts are not lossless.',code=ErrorCode.CONTRACT_INVALID)
        if encoded_size(wire) > 32768:
            raise model_failure('Compact facts too large; nothing omitted.',code=ErrorCode.CONTRACT_INVALID)
        self._compact_json = canonical(wire)
        self.facts_sha256 = wire['facts_sha256']

    def _expand_wire(self,wire):
        extra = {'codec','facts_sha256','facts','sources','provenances','findings'}
        decode = lambda value: ReferenceCodec.decode(value,wire['sources'],wire['provenances'])
        original = {key:decode(value) for key,value in wire.items() if key not in extra}
        original['fact_catalog'] = {row[0]:decode(row[1]) for row in wire['facts'].values()}
        original['findings'] = [{'finding_key':self._full_keys[item['id']],
            'category':item['category'],'campsite_id':item['campsite_id'],
            'fact_refs':[wire['facts'][alias][0] for alias in item['facts']],
            'allowed_actions':item['actions']} for item in wire['findings']]
        return original

    def expanded_facts(self):
        return self._expand_wire(self.read_safety_facts())

    def read_safety_facts(self):
        return strict_json(self._compact_json)

    def expanded_proposal(self,raw):
        def failure(stage, **detail):
            return proposal_failure(stage, aliases=self._full_keys,
                run_id=self.input.version_context.run_id, **detail)
        try:
            proposal = CompactProposal.model_validate(raw)
        except (ValueError, TypeError, KeyError):
            raise failure('PROPOSAL_SCHEMA') from None
        if proposal.facts_sha256 != self.facts_sha256:
            raise failure('FACT_IDENTITY')
        if {item.id for item in proposal.findings} != set(self._full_keys):
            raise failure('FINDING_COVERAGE', expected=list(self._full_keys.values()),
                provided=[self._full_keys.get(item.id, '<unknown_finding>') for item in proposal.findings])
        try:
            return SafetyProposal(findings=[{'finding_key':self._full_keys[item.id],
                'action_code':item.action,'interpretation_unverified':item.advice,
                'action_unverified':item.advice} for item in proposal.findings],
                action_priority=[self._full_keys[key] for key in proposal.priority],
                decision_summary_unverified=proposal.summary)
        except (ValueError,TypeError,KeyError):
            raise failure('PROPOSAL_SCHEMA') from None

    def evaluate_compact_plan(self,raw):
        return super().evaluate_safety_plan(self.expanded_proposal(raw))

    def compact_from_plan(self,plan):
        plan = ValidatedSafetyPlan.model_validate(plan)
        if any(item.interpretation_unverified != item.action_unverified for item in plan.findings):
            raise ValueError('One advice sentence, not a second invented explanation')
        return CompactProposal(facts_sha256=self.facts_sha256,
            findings=[{'id':self._short_keys[item.finding_key],'action':item.action_code,
                'advice':item.action_unverified} for item in plan.findings],
            priority=[self._short_keys[key] for key in plan.action_priority],
            summary=plan.decision_summary_unverified)
