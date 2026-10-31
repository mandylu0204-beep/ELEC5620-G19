from contextlib import contextmanager
from pathlib import Path
import sqlite3

from ..contracts.enums import ErrorCode, AllowedAction
from ..contracts.errors import ContractError, ContractFailure


MIGRATION_1 = """
CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE users(
 id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('CAMPER','FOUNDER')), password_hash TEXT NOT NULL);
CREATE TABLE sessions(
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 csrf_hash TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE profiles(
 owner_id TEXT PRIMARY KEY REFERENCES users(id), profile_id TEXT NOT NULL UNIQUE,
 payload TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 1), updated_at TEXT NOT NULL);
CREATE TABLE requests(
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), raw_text TEXT NOT NULL,
 status TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
 confirmed_context TEXT, created_at TEXT NOT NULL, UNIQUE(owner_id,id));
CREATE TABLE plans(
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL,
 current_version_id TEXT, active_run_id TEXT, final_version_id TEXT, created_at TEXT NOT NULL,
 FOREIGN KEY(owner_id,request_id) REFERENCES requests(owner_id,id),
 FOREIGN KEY(id,current_version_id) REFERENCES versions(plan_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(id,final_version_id) REFERENCES versions(plan_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(id,active_run_id) REFERENCES runs(plan_id,id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE runs(
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id), request_id TEXT NOT NULL REFERENCES requests(id),
 scope TEXT NOT NULL, confirmed_context TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL, UNIQUE(plan_id,id));
CREATE TABLE versions(
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans(id), version_number INTEGER NOT NULL CHECK(version_number >= 1),
 content TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 UNIQUE(plan_id,id), UNIQUE(plan_id,version_number));
CREATE TABLE run_versions(
 run_id TEXT PRIMARY KEY, version_id TEXT NOT NULL, plan_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, UNIQUE(run_id,version_id),
 FOREIGN KEY(plan_id,run_id) REFERENCES runs(plan_id,id),
 FOREIGN KEY(plan_id,version_id) REFERENCES versions(plan_id,id));
CREATE TABLE recommendations(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE REFERENCES runs(id), payload TEXT NOT NULL);
CREATE TABLE assessments(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL, version_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('LOGISTICS','SAFETY')), payload TEXT NOT NULL,
 depends_on_id TEXT, created_at TEXT NOT NULL, UNIQUE(run_id,kind), UNIQUE(run_id,version_id,id),
 FOREIGN KEY(run_id,version_id) REFERENCES run_versions(run_id,version_id),
 FOREIGN KEY(run_id,version_id,depends_on_id) REFERENCES assessments(run_id,version_id,id));
CREATE TABLE gear_checklists(
 id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL UNIQUE REFERENCES assessments(id), payload TEXT NOT NULL);
CREATE TABLE reviews(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL, version_id TEXT NOT NULL,
 reviewer_id TEXT NOT NULL REFERENCES users(id), payload TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(run_id,version_id) REFERENCES run_versions(run_id,version_id));
CREATE TABLE run_events(
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), stage TEXT NOT NULL,
 status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL);
CREATE TABLE write_receipts(
 run_id TEXT NOT NULL REFERENCES runs(id), write_key TEXT NOT NULL,
 operation TEXT NOT NULL, input_hash TEXT NOT NULL, result TEXT NOT NULL,
 PRIMARY KEY(run_id,write_key));
CREATE TABLE final_records(
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, version_id TEXT NOT NULL,
 run_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(plan_id,version_id) REFERENCES versions(plan_id,id),
 FOREIGN KEY(run_id,version_id) REFERENCES run_versions(run_id,version_id));
CREATE TRIGGER immutable_version_content BEFORE UPDATE OF content,plan_id,version_number ON versions
 BEGIN SELECT RAISE(ABORT, 'immutable version content'); END;
CREATE TRIGGER immutable_assessment BEFORE UPDATE ON assessments
 BEGIN SELECT RAISE(ABORT, 'immutable assessment'); END;
CREATE TRIGGER immutable_run_binding BEFORE UPDATE ON run_versions
 BEGIN SELECT RAISE(ABORT, 'immutable run binding'); END;
CREATE TRIGGER immutable_run_input BEFORE UPDATE OF scope,confirmed_context ON runs
 BEGIN SELECT RAISE(ABORT, 'immutable run input'); END;
CREATE TRIGGER immutable_confirmed_request BEFORE UPDATE ON requests
 WHEN OLD.status = 'CONFIRMED' BEGIN SELECT RAISE(ABORT, 'immutable confirmed request'); END;
"""

MIGRATION_2 = """
CREATE TABLE request_summaries(
 request_id TEXT PRIMARY KEY REFERENCES requests(id), analysis_revision INTEGER NOT NULL,
 profile_revision INTEGER NOT NULL, profile_snapshot TEXT NOT NULL,
 demo_context TEXT NOT NULL, dataset_context TEXT NOT NULL,
 result TEXT, error TEXT);
CREATE TABLE request_confirmations(
 request_id TEXT PRIMARY KEY REFERENCES requests(id), owner_id TEXT NOT NULL REFERENCES users(id),
 command_key TEXT NOT NULL, input_hash TEXT NOT NULL, confirmed_at TEXT NOT NULL,
 UNIQUE(owner_id,command_key));
CREATE TRIGGER immutable_confirmation BEFORE UPDATE ON request_confirmations
 BEGIN SELECT RAISE(ABORT, 'immutable confirmation'); END;
CREATE TRIGGER immutable_confirmed_summary BEFORE UPDATE ON request_summaries
 WHEN (SELECT status FROM requests WHERE id=OLD.request_id)='CONFIRMED'
 BEGIN SELECT RAISE(ABORT, 'immutable confirmed summary'); END;
CREATE TRIGGER no_delete_confirmed_summary BEFORE DELETE ON request_summaries
 WHEN (SELECT status FROM requests WHERE id=OLD.request_id)='CONFIRMED'
 BEGIN SELECT RAISE(ABORT, 'immutable confirmed summary'); END;
"""


MIGRATION_3 = """
CREATE TABLE review_commands(
 reviewer_id TEXT NOT NULL REFERENCES users(id), command_key TEXT NOT NULL,
 review_id TEXT NOT NULL UNIQUE REFERENCES reviews(id), input_hash TEXT NOT NULL,
 result TEXT NOT NULL, PRIMARY KEY(reviewer_id,command_key));
CREATE TRIGGER immutable_review BEFORE UPDATE ON reviews
 BEGIN SELECT RAISE(ABORT, 'immutable review'); END;
CREATE TRIGGER immutable_review_command BEFORE UPDATE ON review_commands
 BEGIN SELECT RAISE(ABORT, 'immutable review command'); END;
"""


MIGRATION_4 = """
CREATE UNIQUE INDEX final_once_per_evidence ON final_records(run_id,version_id);
CREATE TABLE final_commands(
 owner_id TEXT NOT NULL REFERENCES users(id), command_key TEXT NOT NULL,
 final_id TEXT NOT NULL REFERENCES final_records(id), input_hash TEXT NOT NULL,
 result TEXT NOT NULL, PRIMARY KEY(owner_id,command_key));
CREATE TRIGGER immutable_final BEFORE UPDATE ON final_records
 BEGIN SELECT RAISE(ABORT, 'immutable final snapshot'); END;
CREATE TRIGGER no_delete_final BEFORE DELETE ON final_records
 BEGIN SELECT RAISE(ABORT, 'immutable final snapshot'); END;
CREATE TRIGGER immutable_final_command BEFORE UPDATE ON final_commands
 BEGIN SELECT RAISE(ABORT, 'immutable final command'); END;
"""


MIGRATION_5 = """
CREATE TABLE workflow_commands(
 owner_id TEXT NOT NULL REFERENCES users(id), command_key TEXT NOT NULL,
 operation TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id),
 input_hash TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(owner_id,command_key));
CREATE TABLE run_leases(
 run_id TEXT PRIMARY KEY REFERENCES runs(id), attempt_id TEXT NOT NULL UNIQUE,
 generation INTEGER NOT NULL CHECK(generation >= 1), expires_at REAL NOT NULL);
CREATE TRIGGER immutable_workflow_command BEFORE UPDATE ON workflow_commands
 BEGIN SELECT RAISE(ABORT, 'immutable workflow command'); END;
CREATE TRIGGER no_delete_workflow_command BEFORE DELETE ON workflow_commands
 BEGIN SELECT RAISE(ABORT, 'immutable workflow command'); END;
"""


MIGRATION_6 = """
CREATE TABLE model_planning_traces(
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, run_id TEXT NOT NULL UNIQUE,
 version_id TEXT NOT NULL, owner_id TEXT NOT NULL REFERENCES users(id),
 input_fingerprint TEXT NOT NULL, attempt_id TEXT NOT NULL,
 payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(plan_id,version_id) REFERENCES versions(plan_id,id),
 FOREIGN KEY(run_id,version_id) REFERENCES run_versions(run_id,version_id));
CREATE TRIGGER immutable_model_trace BEFORE UPDATE ON model_planning_traces
 BEGIN SELECT RAISE(ABORT, 'immutable model trace'); END;
CREATE TRIGGER no_delete_model_trace BEFORE DELETE ON model_planning_traces
 BEGIN SELECT RAISE(ABORT, 'immutable model trace'); END;
"""


MIGRATION_7 = """
CREATE TABLE model_logistics_audits(
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
 plan_id TEXT NOT NULL, run_id TEXT NOT NULL UNIQUE, version_id TEXT NOT NULL,
 assessment_id TEXT NOT NULL UNIQUE, gear_checklist_id TEXT NOT NULL UNIQUE REFERENCES gear_checklists(id),
 attempt_id TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
 configuration_fingerprint TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(plan_id,version_id) REFERENCES versions(plan_id,id),
 FOREIGN KEY(run_id,version_id,assessment_id) REFERENCES assessments(run_id,version_id,id));
CREATE TRIGGER immutable_logistics_audit BEFORE UPDATE ON model_logistics_audits
 BEGIN SELECT RAISE(ABORT, 'immutable logistics audit'); END;
CREATE TRIGGER no_delete_logistics_audit BEFORE DELETE ON model_logistics_audits
 BEGIN SELECT RAISE(ABORT, 'immutable logistics audit'); END;
"""


MIGRATION_10 = """
CREATE TABLE model_safety_audits(
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
 plan_id TEXT NOT NULL, run_id TEXT NOT NULL UNIQUE, version_id TEXT NOT NULL,
 assessment_id TEXT NOT NULL UNIQUE, depends_on_assessment_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
 configuration_fingerprint TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL, payload TEXT NOT NULL,
 FOREIGN KEY(plan_id,version_id) REFERENCES versions(plan_id,id),
 FOREIGN KEY(run_id,version_id,assessment_id) REFERENCES assessments(run_id,version_id,id),
 FOREIGN KEY(run_id,version_id,depends_on_assessment_id) REFERENCES assessments(run_id,version_id,id));
CREATE TRIGGER immutable_safety_audit BEFORE UPDATE ON model_safety_audits
 BEGIN SELECT RAISE(ABORT, 'immutable safety audit'); END;
CREATE TRIGGER no_delete_safety_audit BEFORE DELETE ON model_safety_audits
 BEGIN SELECT RAISE(ABORT, 'immutable safety audit'); END;
"""


MIGRATION_11 = """
CREATE TABLE trip_series(
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
 current_plan_id TEXT REFERENCES plans(id), revision INTEGER NOT NULL CHECK(revision>=1),
 deleted_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE plan_series_members(
 plan_id TEXT PRIMARY KEY REFERENCES plans(id), series_id TEXT NOT NULL REFERENCES trip_series(id),
 predecessor_plan_id TEXT REFERENCES plans(id), created_at TEXT NOT NULL);
CREATE INDEX series_members ON plan_series_members(series_id);
CREATE TABLE successor_requests(
 request_id TEXT PRIMARY KEY REFERENCES requests(id), series_id TEXT NOT NULL REFERENCES trip_series(id),
 predecessor_plan_id TEXT NOT NULL REFERENCES plans(id), source_context TEXT NOT NULL);
CREATE TABLE successor_commands(
 owner_id TEXT NOT NULL REFERENCES users(id), command_key TEXT NOT NULL, input_hash TEXT NOT NULL,
 request_id TEXT NOT NULL REFERENCES successor_requests(request_id), PRIMARY KEY(owner_id,command_key));
CREATE TABLE series_delete_commands(
 owner_id TEXT NOT NULL REFERENCES users(id), command_key TEXT NOT NULL, input_hash TEXT NOT NULL,
 series_id TEXT NOT NULL REFERENCES trip_series(id), PRIMARY KEY(owner_id,command_key));
CREATE TABLE series_replacements(
 id TEXT PRIMARY KEY, series_id TEXT NOT NULL REFERENCES trip_series(id),
 old_plan_id TEXT NOT NULL REFERENCES plans(id), old_run_id TEXT REFERENCES runs(id),
 old_version_id TEXT REFERENCES versions(id), new_plan_id TEXT NOT NULL REFERENCES plans(id),
 new_run_id TEXT NOT NULL REFERENCES runs(id), created_at TEXT NOT NULL);
CREATE TRIGGER immutable_series_member BEFORE UPDATE ON plan_series_members
 BEGIN SELECT RAISE(ABORT, 'immutable series member'); END;
CREATE TRIGGER immutable_successor_origin BEFORE UPDATE ON successor_requests
 BEGIN SELECT RAISE(ABORT, 'immutable successor origin'); END;
CREATE TRIGGER immutable_successor_command BEFORE UPDATE ON successor_commands
 BEGIN SELECT RAISE(ABORT, 'immutable successor command'); END;
CREATE TRIGGER immutable_series_replacement BEFORE UPDATE ON series_replacements
 BEGIN SELECT RAISE(ABORT, 'immutable series replacement'); END;
CREATE TRIGGER immutable_series_delete_command BEFORE UPDATE ON series_delete_commands
 BEGIN SELECT RAISE(ABORT, 'immutable series delete command'); END;
CREATE TRIGGER no_delete_series_member BEFORE DELETE ON plan_series_members
 BEGIN SELECT RAISE(ABORT, 'immutable series member'); END;
CREATE TRIGGER no_delete_successor_origin BEFORE DELETE ON successor_requests
 BEGIN SELECT RAISE(ABORT, 'immutable successor origin'); END;
CREATE TRIGGER no_delete_successor_command BEFORE DELETE ON successor_commands
 BEGIN SELECT RAISE(ABORT, 'immutable successor command'); END;
CREATE TRIGGER no_delete_series_replacement BEFORE DELETE ON series_replacements
 BEGIN SELECT RAISE(ABORT, 'immutable series replacement'); END;
CREATE TRIGGER no_delete_series_delete_command BEFORE DELETE ON series_delete_commands
 BEGIN SELECT RAISE(ABORT, 'immutable series delete command'); END;
"""


MIGRATION_12 = """
CREATE TABLE requirement_help_tasks(
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(id),
 owner_id TEXT NOT NULL REFERENCES users(id), request_revision INTEGER NOT NULL,
 profile_revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PENDING','PROPOSED','RETURNED','APPLIED')),
 revision INTEGER NOT NULL DEFAULT 1, response TEXT, created_at TEXT NOT NULL,
 UNIQUE(request_id,request_revision,profile_revision));
CREATE TABLE requirement_help_commands(
 actor_id TEXT NOT NULL REFERENCES users(id),command_key TEXT NOT NULL,
 operation TEXT NOT NULL,input_hash TEXT NOT NULL,task_id TEXT NOT NULL REFERENCES requirement_help_tasks(id),
 result TEXT NOT NULL,PRIMARY KEY(actor_id,command_key));
CREATE TABLE requirement_help_events(
 id INTEGER PRIMARY KEY,task_id TEXT NOT NULL REFERENCES requirement_help_tasks(id),
 actor_id TEXT NOT NULL REFERENCES users(id),operation TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TRIGGER immutable_requirement_help_snapshot BEFORE UPDATE OF request_id,owner_id,request_revision,profile_revision,snapshot,created_at ON requirement_help_tasks
 BEGIN SELECT RAISE(ABORT, 'immutable requirement help snapshot'); END;
CREATE TRIGGER immutable_requirement_help_event BEFORE UPDATE ON requirement_help_events
 BEGIN SELECT RAISE(ABORT, 'immutable requirement help event'); END;
CREATE TRIGGER no_delete_requirement_help_event BEFORE DELETE ON requirement_help_events
 BEGIN SELECT RAISE(ABORT, 'immutable requirement help event'); END;
CREATE TRIGGER immutable_requirement_help_command BEFORE UPDATE ON requirement_help_commands
 BEGIN SELECT RAISE(ABORT, 'immutable requirement help command'); END;
CREATE TRIGGER no_delete_requirement_help_command BEFORE DELETE ON requirement_help_commands
 BEGIN SELECT RAISE(ABORT, 'immutable requirement help command'); END;
"""


MIGRATION_13 = """
CREATE TABLE revision_proposals(
 id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES plans(id),
 base_run_id TEXT NOT NULL,base_version_id TEXT NOT NULL,
 base_run_revision INTEGER NOT NULL,base_version_revision INTEGER NOT NULL,
 candidate_run_id TEXT NOT NULL UNIQUE,decision TEXT CHECK(decision IN ('ADOPT','KEEP')),
 revision INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,
 FOREIGN KEY(plan_id,base_run_id) REFERENCES runs(plan_id,id),
 FOREIGN KEY(plan_id,candidate_run_id) REFERENCES runs(plan_id,id),
 FOREIGN KEY(plan_id,base_version_id) REFERENCES versions(plan_id,id));
CREATE UNIQUE INDEX one_pending_revision ON revision_proposals(plan_id) WHERE decision IS NULL;
CREATE TABLE revision_choice_commands(
 owner_id TEXT NOT NULL REFERENCES users(id),command_key TEXT NOT NULL,
 input_hash TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(owner_id,command_key));
CREATE TRIGGER immutable_revision_origin BEFORE UPDATE OF plan_id,base_run_id,base_version_id,
 base_run_revision,base_version_revision,candidate_run_id,created_at ON revision_proposals
 BEGIN SELECT RAISE(ABORT, 'immutable revision origin'); END;
CREATE TRIGGER immutable_revision_decision BEFORE UPDATE ON revision_proposals
 WHEN OLD.decision IS NOT NULL BEGIN SELECT RAISE(ABORT, 'immutable revision decision'); END;
CREATE TRIGGER no_delete_revision_proposal BEFORE DELETE ON revision_proposals
 BEGIN SELECT RAISE(ABORT, 'immutable revision proposal'); END;
CREATE TRIGGER immutable_revision_choice BEFORE UPDATE ON revision_choice_commands
 BEGIN SELECT RAISE(ABORT, 'immutable revision choice'); END;
CREATE TRIGGER no_delete_revision_choice BEFORE DELETE ON revision_choice_commands
 BEGIN SELECT RAISE(ABORT, 'immutable revision choice'); END;
"""


MIGRATION_14 = """
CREATE TABLE review_assistance_notes(
 id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES plans(id),
 run_id TEXT NOT NULL,version_id TEXT NOT NULL,actor_id TEXT NOT NULL REFERENCES users(id),
 payload TEXT NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(plan_id,run_id) REFERENCES runs(plan_id,id),
 FOREIGN KEY(plan_id,version_id) REFERENCES versions(plan_id,id));
CREATE INDEX review_assistance_context ON review_assistance_notes(plan_id,run_id,version_id);
CREATE TABLE review_assistance_commands(
 actor_id TEXT NOT NULL REFERENCES users(id),command_key TEXT NOT NULL,input_hash TEXT NOT NULL,
 note_id TEXT NOT NULL REFERENCES review_assistance_notes(id),result TEXT NOT NULL,
 PRIMARY KEY(actor_id,command_key));
CREATE TRIGGER immutable_review_assistance_note BEFORE UPDATE ON review_assistance_notes
 BEGIN SELECT RAISE(ABORT, 'immutable review assistance note'); END;
CREATE TRIGGER no_delete_review_assistance_note BEFORE DELETE ON review_assistance_notes
 BEGIN SELECT RAISE(ABORT, 'immutable review assistance note'); END;
CREATE TRIGGER immutable_review_assistance_command BEFORE UPDATE ON review_assistance_commands
 BEGIN SELECT RAISE(ABORT, 'immutable review assistance command'); END;
CREATE TRIGGER no_delete_review_assistance_command BEFORE DELETE ON review_assistance_commands
 BEGIN SELECT RAISE(ABORT, 'immutable review assistance command'); END;
"""


def execute_migration(connection, script):
    statement = ''
    for line in script.splitlines():
        statement += line + '\n'
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ''


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA synchronous=FULL')
        return connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
            if not exists:
                # Execute inside the existing transaction; executescript would commit it.
                execute_migration(connection, MIGRATION_1)
                connection.execute("INSERT INTO schema_migrations VALUES(1, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
            versions = [row[0] for row in connection.execute('SELECT version FROM schema_migrations ORDER BY version')]
            if versions == [1]:
                execute_migration(connection, MIGRATION_2)
                connection.execute("INSERT INTO schema_migrations VALUES(2, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(2)
            if versions == [1, 2]:
                execute_migration(connection, MIGRATION_3)
                connection.execute("INSERT INTO schema_migrations VALUES(3, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(3)
            if versions == [1, 2, 3]:
                execute_migration(connection, MIGRATION_4)
                connection.execute("INSERT INTO schema_migrations VALUES(4, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(4)
            if versions == [1, 2, 3, 4]:
                execute_migration(connection, MIGRATION_5)
                connection.execute("INSERT INTO schema_migrations VALUES(5, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(5)
            if versions == [1, 2, 3, 4, 5]:
                execute_migration(connection, MIGRATION_6)
                connection.execute("INSERT INTO schema_migrations VALUES(6, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(6)
            if versions == [1, 2, 3, 4, 5, 6]:
                execute_migration(connection, MIGRATION_7)
                connection.execute("INSERT INTO schema_migrations VALUES(7, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(7)
            if versions == [1, 2, 3, 4, 5, 6, 7]:
                connection.execute('ALTER TABLE plans ADD COLUMN deleted_at TEXT')
                connection.execute("INSERT INTO schema_migrations VALUES(8, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(8)
            if versions == [1, 2, 3, 4, 5, 6, 7, 8]:
                connection.execute('CREATE TABLE deleted_requests(request_id TEXT PRIMARY KEY REFERENCES requests(id), deleted_at TEXT NOT NULL)')
                connection.execute("INSERT INTO schema_migrations VALUES(9, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(9)
            if versions == [1, 2, 3, 4, 5, 6, 7, 8, 9]:
                execute_migration(connection, MIGRATION_10)
                connection.execute("INSERT INTO schema_migrations VALUES(10, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(10)
            if versions == list(range(1, 11)):
                execute_migration(connection, MIGRATION_11)
                connection.execute("INSERT INTO schema_migrations VALUES(11, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(11)
            if versions == list(range(1, 12)):
                execute_migration(connection, MIGRATION_12)
                connection.execute("INSERT INTO schema_migrations VALUES(12, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(12)
            if versions == list(range(1, 13)):
                execute_migration(connection, MIGRATION_13)
                connection.execute("INSERT INTO schema_migrations VALUES(13, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(13)
            if versions == list(range(1, 14)):
                execute_migration(connection, MIGRATION_14)
                connection.execute("INSERT INTO schema_migrations VALUES(14, strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
                versions.append(14)
            if versions != list(range(1, 15)):
                raise RuntimeError('Unsupported database schema version')

    @contextmanager
    def transaction(self, *, write=True):
        connection = None
        try:
            connection = self.connect()
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            if connection is not None:
                connection.rollback()
            # Structural/association failures require an operator, not another
            # worker or model call. Other IO/locking failures retain recovery.
            text = str(exc).lower()
            permanent = ((getattr(exc, 'sqlite_errorcode', 0) & 255) in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_SCHEMA}
                or any(part in text for part in ('no such table','no such column','unique constraint failed',
                    'foreign key constraint failed','check constraint failed','immutable ')))
            raise ContractFailure(ContractError(
                code=ErrorCode.PERSISTENCE_FAILURE, message='Save or read failed. Transaction rolled back.',
                recoverable=not permanent, allowed_actions=[AllowedAction.CONTACT_OPERATOR if permanent else AllowedAction.RETRY],
            )) from exc
        except BaseException:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def ready(self):
        try:
            with self.transaction(write=False) as connection:
                versions = [row[0] for row in connection.execute('SELECT version FROM schema_migrations ORDER BY version')]
            return versions == list(range(1, 15))
        except ContractFailure:
            return False
