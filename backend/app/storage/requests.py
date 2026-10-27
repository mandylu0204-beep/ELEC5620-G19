import json
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, StrictInt, ValidationError

from ..auth import fail, require_role
from ..contracts.base import ContractModel
from ..contracts.dto import ConfirmedContext, ConfirmedRequirements, DemoContext, InterpretRequestInput, ProfileSnapshot, TripRequirements
from ..contracts.enums import ErrorCode
from .repository import encode, fingerprint, now


_Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
_Version = Annotated[str, Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.-]+$')]
_TokenCount = Annotated[StrictInt, Field(ge=0)]


class RequestInterpretationIdentity(ContractModel):
    """Summary-only registration; never part of a saved workflow identity."""
    component_version: _Version
    prompt_sha256: _Sha256
    schema_version: _Version
    configuration_fingerprint: _Sha256
    requested_model: Literal['campus-qwen']


class RequestInterpretationObservation(ContractModel):
    identity: RequestInterpretationIdentity
    usage: dict[Literal['prompt_tokens', 'completion_tokens', 'total_tokens'], _TokenCount]
    attempts: Annotated[StrictInt, Field(ge=1, le=3)]


class RequestInterpretationMetadata(RequestInterpretationObservation):
    metadata_version: Literal['1.0'] = '1.0'
    analysis_revision: Annotated[StrictInt, Field(ge=1)]
    input_sha256: _Sha256


def request_input_fingerprint(input: InterpretRequestInput):
    # Preserve omitted versus explicitly supplied empty/null request fields.
    # Profile defaults are saved in full by begin_analysis, so use the same
    # full shape here and during confirmation after a process restart.
    return fingerprint({
        'raw_text': input.raw_text,
        'explicit_fields': input.explicit_fields.model_dump(mode='json', exclude_unset=True),
        'profile_snapshot': input.profile_snapshot.model_dump(mode='json') if input.profile_snapshot else None,
        'demo_context': input.demo_context.model_dump(mode='json'),
    })


def _saved_interpretation_input(row, summary):
    return InterpretRequestInput(raw_text=row['raw_text'],
        explicit_fields=TripRequirements.model_validate_json(row['payload']),
        profile_snapshot=ProfileSnapshot.model_validate_json(summary['profile_snapshot']),
        demo_context=DemoContext.model_validate_json(summary['demo_context']))


class RequestRepository:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def own(connection, user, request_id):
        require_role(user, 'CAMPER')
        row = connection.execute('SELECT * FROM requests WHERE id=? AND owner_id=? AND NOT EXISTS (SELECT 1 FROM deleted_requests d WHERE d.request_id=requests.id)', (request_id, user.id)).fetchone()
        if not row:
            fail(ErrorCode.NOT_FOUND, '请求不存在。')
        return row

    @staticmethod
    def check_revision(row, expected):
        if row['revision'] != expected:
            fail(ErrorCode.VERSION_CONFLICT, '请求摘要已变化，请刷新后再操作。')

    def result(self, connection, row):
        summary = connection.execute('SELECT * FROM request_summaries WHERE request_id=?', (row['id'],)).fetchone()
        result = {
            'request_id': row['id'], 'raw_text': row['raw_text'], 'explicit_fields': json.loads(row['payload']),
            'status': row['status'], 'revision': row['revision'], 'created_at': row['created_at'],
            'summary': json.loads(summary['result']) if summary and summary['result'] else None,
            'profile_snapshot': json.loads(summary['profile_snapshot']) if summary else None,
            'profile_revision': summary['profile_revision'] if summary else None,
            'error': json.loads(summary['error']) if summary and summary['error'] else None,
            'confirmed_context': json.loads(row['confirmed_context']) if row['confirmed_context'] else None,
            'planning_available': False,
        }
        origin = connection.execute('SELECT o.*,s.revision FROM successor_requests o JOIN trip_series s ON s.id=o.series_id WHERE o.request_id=? AND s.deleted_at IS NULL', (row['id'],)).fetchone()
        if origin:
            source = connection.execute('SELECT id FROM plans WHERE id=? AND deleted_at IS NULL', (origin['predecessor_plan_id'],)).fetchone()
            result.update(trip_series_id=origin['series_id'], predecessor_plan_id=source['id'] if source else None,
                series_revision=origin['revision'])
            original = connection.execute('SELECT s.profile_revision FROM plans p JOIN request_summaries s ON s.request_id=p.request_id WHERE p.id=?', (origin['predecessor_plan_id'],)).fetchone()
            result['source_profile_revision'] = original['profile_revision'] if original else None
            if source:
                # Read the immutable run named by the origin, not the latest
                # personal profile or an accidentally newer source run.
                context = json.loads(origin['source_context'])
                pinned = connection.execute('SELECT confirmed_context FROM runs WHERE id=? AND plan_id=?',
                    (context['expected_active_run_id'], origin['predecessor_plan_id'])).fetchone()
                if pinned:
                    snapshot = json.loads(pinned['confirmed_context'])
                    result['source_profile_snapshot'] = snapshot['profile_snapshot']
                    result['source_requirements'] = snapshot['requirements']
        return result

    def create(self, user, raw_text, explicit):
        require_role(user, 'CAMPER')
        request_id = uuid4().hex
        with self.db.transaction() as connection:
            connection.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)', (request_id, user.id, raw_text, 'DRAFT', 1, encode(explicit.model_dump(mode='json', exclude_unset=True)), None, now()))
            return self.result(connection, self.own(connection, user, request_id))

    def get(self, user, request_id):
        with self.db.transaction(write=False) as connection:
            return self.result(connection, self.own(connection, user, request_id))

    def list(self, user):
        require_role(user, 'CAMPER')
        with self.db.transaction(write=False) as connection:
            return [dict(row) for row in connection.execute('''SELECT q.id AS request_id,q.status,q.revision,q.raw_text,q.created_at,
                o.series_id AS trip_series_id,CASE WHEN o.request_id IS NULL THEN 0 ELSE 1 END AS is_trip_update
                FROM requests q LEFT JOIN successor_requests o ON o.request_id=q.id
                WHERE q.owner_id=? AND NOT EXISTS (SELECT 1 FROM deleted_requests d WHERE d.request_id=q.id)
                ORDER BY q.created_at DESC''', (user.id,))]

    def delete(self, user, request_id):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            if row['status'] == 'ANALYSING':
                fail(ErrorCode.INVALID_STATE, '请求正在生成摘要，请完成后再删除。')
            # Existing plans keep their immutable confirmed snapshots and history.
            connection.execute('INSERT INTO deleted_requests VALUES(?,?)', (request_id, now()))

    def edit(self, user, request_id, expected_revision, raw_text, explicit):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            from .trip_series import validate_successor
            validate_successor(connection, user, request_id)
            self.check_revision(row, expected_revision)
            if row['status'] == 'CONFIRMED':
                fail(ErrorCode.INVALID_STATE, '已确认需求不能原地修改，请新建请求。')
            connection.execute("UPDATE requests SET raw_text=?,payload=?,status='DRAFT',revision=revision+1 WHERE id=?", (raw_text, encode(explicit.model_dump(mode='json', exclude_unset=True)), request_id))
            connection.execute('DELETE FROM request_summaries WHERE request_id=?', (request_id,))
            return self.result(connection, self.own(connection, user, request_id))

    def begin_analysis(self, user, request_id, expected_revision, demo, dataset):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            from .trip_series import validate_successor
            validate_successor(connection, user, request_id)
            self.check_revision(row, expected_revision)
            if row['status'] in {'CONFIRMED','ANALYSING'}:
                fail(ErrorCode.INVALID_STATE, '此请求已确认或正在处理。')
            saved_profile = connection.execute('SELECT * FROM profiles WHERE owner_id=?', (user.id,)).fetchone()
            profile = ProfileSnapshot.model_validate_json(saved_profile['payload']) if saved_profile else ProfileSnapshot()
            profile_revision = saved_profile['revision'] if saved_profile else 0
            revision = row['revision'] + 1
            connection.execute("UPDATE requests SET status='ANALYSING',revision=? WHERE id=?", (revision, request_id))
            connection.execute('INSERT INTO request_summaries VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET analysis_revision=excluded.analysis_revision,profile_revision=excluded.profile_revision,profile_snapshot=excluded.profile_snapshot,demo_context=excluded.demo_context,dataset_context=excluded.dataset_context,result=NULL,error=NULL', (request_id, revision, profile_revision, encode(profile), encode(demo), encode(dataset), None, None))
            return revision, InterpretRequestInput(raw_text=row['raw_text'], explicit_fields=TripRequirements.model_validate_json(row['payload']), profile_snapshot=profile, demo_context=demo)

    def finish_analysis(self, user, request_id, analysis_revision, result, status, *, interpretation_metadata=None):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            if row['revision'] != analysis_revision or row['status'] != 'ANALYSING':
                fail(ErrorCode.STALE_CONTEXT, '较旧的分析结果未应用；请求已修改。')
            saved = result.model_dump(mode='json')
            if interpretation_metadata is not None:
                metadata = RequestInterpretationMetadata.model_validate(interpretation_metadata)
                summary = connection.execute('SELECT * FROM request_summaries WHERE request_id=?', (request_id,)).fetchone()
                if (not summary or summary['analysis_revision'] != analysis_revision
                        or metadata.analysis_revision != analysis_revision
                        or metadata.input_sha256 != request_input_fingerprint(_saved_interpretation_input(row, summary))):
                    fail(ErrorCode.STALE_CONTEXT, '摘要与本次需求资料不一致，请重新生成。')
                saved['interpretation_metadata'] = metadata.model_dump(mode='json')
            connection.execute('UPDATE request_summaries SET result=?,error=NULL WHERE request_id=?', (encode(saved), request_id))
            connection.execute('UPDATE requests SET status=?,revision=revision+1 WHERE id=?', (status.value, request_id))
            return self.result(connection, self.own(connection, user, request_id))

    def fail_analysis(self, user, request_id, analysis_revision, error):
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            if row['revision'] == analysis_revision and row['status'] == 'ANALYSING':
                connection.execute('UPDATE request_summaries SET error=? WHERE request_id=?', (encode(error), request_id))
                connection.execute("UPDATE requests SET status='DRAFT',revision=revision+1 WHERE id=?", (request_id,))

    def confirm(self, user, request_id, expected_revision, command_key, demo, dataset, *, interpretation_identity=None):
        input_hash = fingerprint({'request_id': request_id, 'expected_revision': expected_revision, 'acknowledged': True})
        with self.db.transaction() as connection:
            row = self.own(connection, user, request_id)
            receipt = connection.execute('SELECT * FROM request_confirmations WHERE owner_id=? AND command_key=?', (user.id, command_key)).fetchone()
            if receipt:
                if receipt['request_id'] != request_id or receipt['input_hash'] != input_hash:
                    fail(ErrorCode.IDEMPOTENCY_CONFLICT, '同一确认 key 不能提交不同请求或摘要。')
                return self.result(connection, row)
            from .trip_series import validate_successor
            validate_successor(connection, user, request_id)
            self.check_revision(row, expected_revision)
            if row['status'] != 'AWAITING_CONFIRMATION':
                fail(ErrorCode.INVALID_STATE, '请先完成澄清并查看最新摘要。')
            summary = connection.execute('SELECT * FROM request_summaries WHERE request_id=?', (request_id,)).fetchone()
            profile = connection.execute('SELECT revision FROM profiles WHERE owner_id=?', (user.id,)).fetchone()
            if not summary or not profile or profile['revision'] != summary['profile_revision']:
                fail(ErrorCode.VERSION_CONFLICT, '露营资料已修改，请重新生成摘要后确认。')
            if summary['dataset_context'] != encode(dataset) or summary['demo_context'] != encode(demo):
                fail(ErrorCode.STALE_CONTEXT, '数据或演示上下文已变化，请重新生成摘要。')
            result = json.loads(summary['result'])
            if 'interpretation_metadata' in result:
                try:
                    metadata = RequestInterpretationMetadata.model_validate(result['interpretation_metadata'])
                    current_identity = RequestInterpretationIdentity.model_validate(interpretation_identity)
                    matches = (metadata.identity == current_identity
                        and metadata.analysis_revision == summary['analysis_revision']
                        and metadata.input_sha256 == request_input_fingerprint(_saved_interpretation_input(row, summary)))
                except (ValidationError, ValueError, TypeError):
                    matches = False
                if not matches:
                    fail(ErrorCode.STALE_CONTEXT, '需求理解结果或配置已变化，请重新生成摘要。')
            context = ConfirmedContext(request_id=request_id, confirmed_at=now(), requirements=ConfirmedRequirements.model_validate(result['extracted_requirements']), profile_snapshot=ProfileSnapshot.model_validate_json(summary['profile_snapshot']), demo_context=demo, dataset_context=dataset)
            from ..agents.rules.transport import require_supported
            require_supported(context.profile_snapshot, dataset)
            connection.execute('INSERT INTO request_confirmations VALUES(?,?,?,?,?)', (request_id, user.id, command_key, input_hash, context.confirmed_at.isoformat()))
            connection.execute("UPDATE requests SET status='CONFIRMED',revision=revision+1,confirmed_context=? WHERE id=?", (encode(context), request_id))
            return self.result(connection, self.own(connection, user, request_id))
