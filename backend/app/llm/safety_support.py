"""Closed live safety protocol matrix, independent of client/configuration IO."""
from types import MappingProxyType

SAFETY_PROTOCOLS = MappingProxyType({
    '2.1.0': ('campus-safety-advisory-agent-2', 'safety-read-only-tools-2', 'safety-advisory-validation-2'),
    '2.2.0': ('campus-safety-advisory-agent-3', 'safety-read-only-tools-3', 'safety-advisory-validation-3'),
})


def matches_live_protocol(dataset_version, seed):
    expected = SAFETY_PROTOCOLS.get(dataset_version)
    return expected is not None and tuple(seed.get(key) for key in (
        'agent_version', 'tool_version', 'validation_version')) == expected
