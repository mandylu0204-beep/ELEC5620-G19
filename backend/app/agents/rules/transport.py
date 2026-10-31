"""Small, explicitly registered transport policy; no timetable or routing IO."""
from .common import input_failure
from ...contracts.enums import ErrorCode
from ...contracts.errors import ContractError, ContractFailure

POLICY_KEY = 'b_transport_policy'
MINIMAL_POLICY_VERSION = 'public-transport-minimal-1'
POLICY_VERSION = 'system-trip-preparation-2'
SUPPORTED_MODES = ('CAR', 'PUBLIC_TRANSPORT')


def checked_policy(value):
    # Absent marker means historical behavior, never silently upgrade it.
    if value not in {None, MINIMAL_POLICY_VERSION, POLICY_VERSION}:
        raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT,
            message='Unsupported transport-check policy version. Contact the maintainer.'))
    return value


def require_supported(profile, context):
    if checked_policy(context.selection_config.get(POLICY_KEY)) is not None:
        if profile is None or profile.transport.transport_type not in SUPPORTED_MODES:
            raise input_failure('Only car and public transport are supported. Select a mode in your profile, then regenerate the request summary.',
                'transport.transport_type')
