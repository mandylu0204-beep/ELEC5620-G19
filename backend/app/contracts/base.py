from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictInt

SCHEMA_VERSION = "1.0"
DEMO_DISCLAIMER = (
    "This prototype uses synthetic demonstration data. It must not be used for "
    "real trip planning, campsite availability, or safety decisions."
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, revalidate_instances="always")


def decimal_from_text(value: object) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise ValueError("Decimal quantities must use decimal strings, not JSON numbers")
    try:
        result = Decimal(value)
    except ArithmeticError as exc:
        raise ValueError("Invalid decimal quantity") from exc
    if not result.is_finite():
        raise ValueError("Decimal quantity must be finite")
    return result


Quantity = Annotated[Decimal, BeforeValidator(decimal_from_text, json_schema_input_type=str), Field(ge=0)]
MoneyCents = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
