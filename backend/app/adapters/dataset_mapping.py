"""Conservative v1 boundary conversions, never inference from test labels."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re

from ..contracts.dto import EquipmentItem

UNKNOWN_TEXT = {'', 'unknown'}
WORD_NUMBERS = {'one': 1, 'two': 2, 'three': 3, 'four': 4}
EQUIPMENT_KEYS = {
    'family tent': 'tent', 'first aid kit': 'first_aid_kit', 'torch': 'torch',
    'camping stove': 'camping_stove', 'car': 'vehicle',
}
COST_CATEGORIES = {
    'Campsite': 'CAMPSITE', 'Transport': 'TRANSPORT', 'Food': 'FOOD',
    'Water': 'WATER', 'Additional Equipment': 'ADDITIONAL_GEAR',
}


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Expected text')
    value = value.strip()
    return None if value.casefold() in UNKNOWN_TEXT else value


def required_text(value: object) -> str:
    text = optional_text(value)
    if text is None:
        raise ValueError('Required text is missing')
    return text


def decimal_value(value: object) -> Decimal | None:
    if value is None or isinstance(value, str) and value.strip().casefold() in UNKNOWN_TEXT:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('Numbers must originate from decimal text, not float or bool')
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError('Number must be finite')
    return number


def aud_to_cents(value: object) -> int | None:
    """Unknown remains None; explicit zero is zero; negative money is invalid."""
    number = decimal_value(value)
    if number is None:
        return None
    if number < 0:
        raise ValueError('Money cannot be negative')
    return int((number * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def optional_integer(value: object) -> int | None:
    number = decimal_value(value)
    if number is None:
        return None
    if number != number.to_integral_value():
        raise ValueError('Expected an integer')
    return int(number)


def source_date(value: object) -> date | None:
    text = optional_text(value)
    if text is None:
        return None
    result = date.fromisoformat(text)
    if result.isoformat() != text:
        raise ValueError('Dates must use YYYY-MM-DD')
    return result


def csv_boolean(value: object) -> bool | None:
    text = optional_text(value)
    if text is None:
        return None
    if text.casefold() not in {'true', 'false'}:
        raise ValueError('CSV boolean must be true, false or unknown')
    return text.casefold() == 'true'


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError('Expected a list of strings')
    return [required_text(item) for item in value]


def csv_list(value: object) -> list[str]:
    text = optional_text(value)
    return [required_text(item) for item in text.split(';')] if text is not None else []


def normalize_equipment(label: str) -> EquipmentItem:
    """Extract only explicit count/capacity phrases; possession is not confirmation."""
    label = required_text(label)
    normalized = label.casefold()
    quantity, capacity = None, None
    tent = re.fullmatch(r'(one|two|three|four|[1-9][0-9]*)-person tent', normalized)
    bags = re.fullmatch(r'(one|two|three|four|[1-9][0-9]*) sleeping bags?', normalized)
    if tent:
        token = tent.group(1)
        capacity = WORD_NUMBERS[token] if token in WORD_NUMBERS else int(token)
        item_key, quantity = 'tent', 1
    elif bags:
        token = bags.group(1)
        item_key = 'sleeping_bag'
        quantity = WORD_NUMBERS[token] if token in WORD_NUMBERS else int(token)
    else:
        # Preserve unsupported labels, but never pretend they fulfil a known rule.
        item_key = EQUIPMENT_KEYS.get(normalized)
        if item_key is None:
            item_key = 'unmapped_' + re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')
    return EquipmentItem(
        item_key=item_key, label=label, quantity=quantity,
        unit='vehicle' if item_key == 'vehicle' else 'item',
        capacity_persons=capacity, confirmed=False,
    )
