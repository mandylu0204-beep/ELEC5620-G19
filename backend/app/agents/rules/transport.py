"""Small, explicitly registered transport policy; no timetable or routing IO."""
from .common import input_failure
from ...contracts.enums import ErrorCode
from ...contracts.errors import ContractError, ContractFailure

POLICY_KEY = 'b_transport_policy'
POLICY_VERSION = 'public-transport-minimal-1'
SUPPORTED_MODES = ('CAR', 'PUBLIC_TRANSPORT')


def checked_policy(value):
    # Absent marker means historical behavior, never silently upgrade it.
    if value not in {None, POLICY_VERSION}:
        raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT,
            message='交通检查规则版本不受支持，请联系项目负责人。'))
    return value


def require_supported(profile, context):
    if checked_policy(context.selection_config.get(POLICY_KEY)) is not None:
        if profile is None or profile.transport.transport_type not in SUPPORTED_MODES:
            raise input_failure('当前仅支持自驾或公共交通。请在个人资料中明确交通方式，再重新生成需求摘要。',
                'transport.transport_type')
