# CampMate Synthetic Data Dictionary

All values are synthetic demonstration data. `unknown` is used when a value is not available. Every record requires `source_type`, `source_name`, `source_date`, `demo_only`, and `notes`.

## synthetic_campsites.csv

| Field | Type | Required | Allowed values / format | Example | Missing-value handling | Module |
|---|---|---|---|---|---|---|
| campsite_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| region | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| subregion | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| latitude | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| longitude | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| nightly_fee_aud | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| fee_unit | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| booking_required | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| vehicle_access | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| public_transport_access | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| max_group_size | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| toilets | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| potable_water | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| showers | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| fire_allowed | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| pets_allowed | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| wheelchair_accessible | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| supported_seasons | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| facilities | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| mandatory_restrictions | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| risk_tags | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| demo_only | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| notes | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |

## synthetic_gear_rules.csv

| Field | Type | Required | Allowed values / format | Example | Missing-value handling | Module |
|---|---|---|---|---|---|---|
| gear_rule_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| category | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| item_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| trigger_conditions | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| quantity_rule | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| essential | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| severity_if_missing | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| substitute_allowed | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| substitute_example | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| reason | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| demo_only | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| notes | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |

## synthetic_cost_reference.csv

| Field | Type | Required | Allowed values / format | Example | Missing-value handling | Module |
|---|---|---|---|---|---|---|
| cost_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| category | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| item_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| unit | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| low_aud | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| typical_aud | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| high_aud | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| calculation_rule | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| demo_only | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| assumption | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| notes | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |

## synthetic_profiles.json

| Field | Type | Required | Allowed values / format | Example | Missing-value handling | Module |
|---|---|---|---|---|---|---|
| profile_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| camper_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| group_size | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| experience_level | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| has_children | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| available_equipment | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| transport_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| accessibility_requirements | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| demo_only | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| notes | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |

## synthetic_requests.json

| Field | Type | Required | Allowed values / format | Example | Missing-value handling | Module |
|---|---|---|---|---|---|---|
| request_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| profile_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| natural_language_request | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| destination | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| start_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| duration_days | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| budget_aud | number | Yes | Non-negative number unless stated otherwise | 2 | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| preferences | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| expected_request_status | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| missing_fields | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| demo_only | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| notes | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |

## synthetic_safety_scenarios.json

| Field | Type | Required | Allowed values / format | Example | Missing-value handling | Module |
|---|---|---|---|---|---|---|
| safety_case_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| title | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| campsite_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| scenario_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| weather | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| fire | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| road_access | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| campsite_restrictions | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| risk_tags | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| severity | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| confidence | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| mandatory_blockers | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| expected_outcome | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| expected_actions | array | Yes | JSON array / semicolon list in CSV | ["quiet"] | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_name | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| source_date | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| demo_only | boolean | Yes | true or false | true | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| notes | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |

## synthetic_agent_test_cases.csv

| Field | Type | Required | Allowed values / format | Example | Missing-value handling | Module |
|---|---|---|---|---|---|---|
| test_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| requirement_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| module | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| title | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| priority | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| preconditions | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| profile_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| request_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| campsite_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| safety_case_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| plan_version_id | string | Yes | lowercase letters, digits, hyphens | demo-pine-camp | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| execution_steps | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| expected_extracted_values | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| expected_outcome | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| expected_required_content | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| expected_state_change | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| forbidden_behaviour | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| test_type | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |
| pass_criteria | string | Yes | Free text | demo value | Use `unknown`, empty array, or blank CSV field as appropriate | Relevant CampMate module |

## Controlled enums

| Enum | Allowed values |
|---|---|
| Request status | CONFIRMED, NEEDS_CLARIFICATION, REJECTED |
| PlanVersion status | DRAFT, REVISION_REQUIRED, APPROVED, FINALIZED, REJECTED, BLOCKED |
| Assessment status | PASSED, REVIEW, REVISION, BLOCKED |
| Risk level | LOW, MEDIUM, HIGH, CRITICAL |
| Confidence | LOW, MEDIUM, HIGH |
| Human Review decision | APPROVE, REJECT, REQUEST_REVISION |
| Data source type | SYNTHETIC |
| Safety data status | AVAILABLE, MISSING, STALE, CONFLICTING |
| Road access status | OPEN, RESTRICTED, CLOSED, UNKNOWN |
