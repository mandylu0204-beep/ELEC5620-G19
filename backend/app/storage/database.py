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
            if versions != [1, 2, 3, 4, 5]:
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
            raise ContractFailure(ContractError(
                code=ErrorCode.PERSISTENCE_FAILURE, message='保存或读取失败，事务已回滚。',
                recoverable=True, allowed_actions=[AllowedAction.RETRY],
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
                return versions == [1, 2, 3, 4, 5]
        except ContractFailure:
            return False
