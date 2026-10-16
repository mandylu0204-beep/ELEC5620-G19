"""The committed A/B handoff schema must match this component exactly."""
import json
from pathlib import Path

from app.llm.safety_contract import safety_contract_document


def test_committed_internal_contract_matches_component():
    path=Path(__file__).resolve().parents[2]/'docs/contracts/safety_advisory_v2.schema.json'
    assert json.loads(path.read_text(encoding='utf-8'))==safety_contract_document()


def test_frozen_v1_bundle_still_matches_its_original_schema():
    from app.llm.safety_v1.safety_contract import safety_contract_document as v1_document
    path=Path(__file__).resolve().parents[2]/'docs/contracts/safety_advisory_v1.schema.json'
    assert json.loads(path.read_text(encoding='utf-8'))==v1_document()
