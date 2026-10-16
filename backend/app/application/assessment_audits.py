"""Aggregate exactly the audits required by enabled roles and saved steps."""
from .logistics_audit import load_audits as load_logistics
from .safety_audit import load_audits as load_safety


def load_audits(connection, scope, version, *, must_exist=False):
    return {**load_logistics(connection,scope,version,must_exist=must_exist),
            **load_safety(connection,scope,version,must_exist=must_exist)}
