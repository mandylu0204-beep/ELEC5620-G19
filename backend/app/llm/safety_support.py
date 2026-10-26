"""Closed live safety protocol matrix, independent of client/configuration IO."""
from types import MappingProxyType

SAFETY_PROTOCOLS = MappingProxyType({
    '2.1.0': ('campus-safety-advisory-agent-2', 'safety-read-only-tools-2', 'safety-advisory-validation-2'),
    '2.2.0': ('campus-safety-advisory-agent-3', 'safety-read-only-tools-3', 'safety-advisory-validation-3'),
})

COMPACT_SAFETY_PROTOCOLS = MappingProxyType({
    '2.2.0': ('campus-safety-advisory-agent-4', 'safety-read-only-tools-4', 'safety-advisory-validation-4'),
})


def selected_protocol(dataset_version, protocol='standard'):
    if protocol == 'standard':
        return SAFETY_PROTOCOLS.get(dataset_version)
    if protocol == 'compact':
        return COMPACT_SAFETY_PROTOCOLS.get(dataset_version)
    return None


def protocol_for_seed(dataset_version, seed):
    if not isinstance(seed, dict):
        return None
    actual = tuple(seed.get(key) for key in ('agent_version', 'tool_version', 'validation_version'))
    for protocol in ('standard', 'compact'):
        expected = selected_protocol(dataset_version, protocol)
        if expected is not None and actual == expected:
            if protocol == 'compact':
                return protocol if seed.get('codec_version') == 'safety-lossless-facts-1' else None
            return protocol if 'codec_version' not in seed else None
    return None


def matches_live_protocol(dataset_version, seed, *, protocol=None):
    actual = protocol_for_seed(dataset_version, seed)
    return actual is not None and (protocol is None or protocol == actual)
