"""A-side input integrity checks. No prose parsing or trip/safety inference."""
import csv
import hashlib
from datetime import timedelta

from ..auth import fail
from ..contracts.dto import Clarification, DatasetContext, InterpretRequestResult, ProfileSnapshot, TripRequirements
from ..contracts.enums import ErrorCode, FieldErrorCode, RequestStatus
from ..contracts.errors import FieldError

BUSINESS_FILES = (
    'synthetic_campsites.csv', 'synthetic_gear_rules.csv', 'synthetic_cost_reference.csv',
    'synthetic_profiles.json', 'synthetic_requests.json', 'synthetic_safety_scenarios.json',
)


def data_context(settings):
    try:
        digests = {name: hashlib.sha256((settings.dataset_path / 'data' / name).read_bytes()).hexdigest() for name in BUSINESS_FILES}
        with (settings.dataset_path / 'data/synthetic_campsites.csv').open(encoding='utf-8-sig', newline='') as source:
            rows = list(csv.DictReader(source))
        if not rows or any(row.get('source_type') != 'SYNTHETIC' or row.get('demo_only', '').lower() != 'true' or not row.get('region', '').strip() for row in rows):
            raise ValueError('Dataset needs synthetic region metadata')
        regions = sorted({row['region'].strip() for row in rows})
        context = DatasetContext(dataset_version='v1', file_digests=digests, rules_version='a-request-normalization-v1')
        return context, regions
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        from ..contracts.errors import ContractError, ContractFailure
        raise ContractFailure(ContractError(code=ErrorCode.ADAPTER_FAILURE, message='无法读取演示来源，需求尚未确认。')) from exc


def normalize(result: InterpretRequestResult, explicit: TripRequirements, profile: ProfileSnapshot, regions: list[str]):
    extracted = result.extracted_requirements.model_dump(mode='json')
    # Explicit user input has authority over interpretation output.
    for field, value in explicit.model_dump(mode='json', exclude_unset=True).items():
        if value is not None:
            extracted[field] = value
    requirements = TripRequirements.model_validate(extracted)
    errors = list(result.field_errors)
    questions = list(result.clarifications)

    def issue(field, message, code=FieldErrorCode.MISSING):
        if not any(item.field == field and item.code == code for item in errors):
            errors.append(FieldError(field=field, code=code, message=message))
        if not any(item.field == field for item in questions):
            questions.append(Clarification(field=field, question=message, reason='确认前必须明确此项。'))

    values = requirements.model_dump()
    destination = (requirements.destination or '').strip()
    if not destination:
        issue('destination', '请选择演示目的地。')
    else:
        canonical = next((region for region in regions if region.casefold() == destination.casefold()), None)
        if canonical is None:
            issue('destination', '目的地不在当前 synthetic 演示范围内，请选择支持的地区。', FieldErrorCode.UNSUPPORTED)
        else:
            values['destination'] = canonical
    if requirements.start_date is None:
        issue('start_date', '请填写开始日期。')
    if requirements.duration_nights is None:
        issue('duration_nights', '请明确晚数；只有天数或日期不能直接替你确认晚数。')
    else:
        days = requirements.duration_nights + 1
        if requirements.duration_days is not None and requirements.duration_days != days:
            issue('duration_days', f'{requirements.duration_nights} 晚应为 {days} 天，请修改冲突的天数。', FieldErrorCode.CONFLICTING)
        else:
            values['duration_days'] = days
        if requirements.start_date is not None:
            try:
                end = requirements.start_date + timedelta(days=requirements.duration_nights)
                if requirements.end_date is not None and requirements.end_date != end:
                    issue('end_date', f'结束日期应为 {end.isoformat()}，请修改冲突的日期。', FieldErrorCode.CONFLICTING)
                else:
                    values['end_date'] = end
            except OverflowError:
                issue('duration_nights', '晚数超出可表示的日期范围，请修改。', FieldErrorCode.INVALID)
    if requirements.budget_cents is None:
        issue('budget_cents', '请填写整个小组的 AUD 预算。')
    if profile.group_size is None:
        issue('profile.group_size', '请先保存小组人数，再重新生成摘要。')
    # A has derived these optional fields; an Agent's missing-only message no longer applies.
    questions = [item for item in questions if not (item.field in {'duration_days','end_date'} and values.get(item.field) is not None and not any(error.field == item.field for error in errors))]
    normalized = InterpretRequestResult.model_validate(result.model_dump(mode='json') | {
        'extracted_requirements': TripRequirements.model_validate(values).model_dump(mode='json'),
        'field_errors': [item.model_dump(mode='json') for item in errors],
        'clarifications': [item.model_dump(mode='json') for item in questions],
    })
    status = RequestStatus.UNSUPPORTED if any(item.code == FieldErrorCode.UNSUPPORTED for item in errors) else RequestStatus.NEEDS_CLARIFICATION if errors or questions else RequestStatus.AWAITING_CONFIRMATION
    return normalized, status
