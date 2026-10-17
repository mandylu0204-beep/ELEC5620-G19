from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
import re
import unicodedata
from uuid import uuid4

from .contracts.enums import ErrorCode
from .contracts.errors import ContractError, ContractFailure
from .storage.database import Database

COOKIE_NAME = 'campmate_session'
PBKDF2_ITERATIONS = 600_000
# Public credentials for the local synthetic demonstration, never real identities.
DEMO_ACCOUNTS = (
    ('camper-a', 'camper.a', 'Camper A', 'CAMPER', 'CampMate-A-2026!'),
    ('camper-b', 'camper.b', 'Camper B', 'CAMPER', 'CampMate-B-2026!'),
    ('founder', 'founder', 'Founder', 'FOUNDER', 'CampMate-Founder-2026!'),
)


def fail(code, message):
    raise ContractFailure(ContractError(code=code, message=message))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${key.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    algorithm, rounds, salt, expected = encoded.split('$')
    if algorithm != 'pbkdf2_sha256':
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(actual.hex(), expected)


@dataclass(frozen=True)
class User:
    id: str
    username: str
    display_name: str
    role: str

    def public(self):
        return {'user_id': self.id, 'username': self.username, 'display_name': self.display_name, 'role': self.role}


class AuthService:
    def __init__(self, database: Database, session_hours: int):
        self.db = database
        self.session_seconds = session_hours * 3600
        self.dummy_hash = hash_password(secrets.token_urlsafe(24))

    def seed_demo_accounts(self):
        with self.db.transaction() as connection:
            for user_id, username, name, role, password in DEMO_ACCOUNTS:
                if connection.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone() is None:
                    connection.execute('INSERT INTO users VALUES(?,?,?,?,?)', (user_id, username, name, role, hash_password(password)))

    def register(self, username: str, display_name: str, password: str):
        username = username.strip().lower()
        display_name = display_name.strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,31}', username):
            fail(ErrorCode.INPUT_INVALID, '用户名请使用 3–32 位英文字母、数字、点、下划线或短横线，以字母或数字开头。')
        if not 1 <= len(display_name) <= 80 or any(unicodedata.category(char).startswith('C') for char in display_name):
            fail(ErrorCode.INPUT_INVALID, '请填写有效昵称，最多 80 个字符。')
        if not 8 <= len(password) <= 256 or not password.strip():
            fail(ErrorCode.INPUT_INVALID, '密码请使用 8–256 个字符，不能全部为空格。')
        encoded = hash_password(password)
        with self.db.transaction() as connection:
            if (username in {item[1] for item in DEMO_ACCOUNTS}
                    or connection.execute('SELECT 1 FROM users WHERE lower(username)=?', (username,)).fetchone()):
                fail(ErrorCode.VERSION_CONFLICT, '此用户名已被使用，请换一个。')
            user = User(uuid4().hex, username, display_name, 'CAMPER')
            connection.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                (user.id, user.username, user.display_name, user.role, encoded))
            return user

    def login(self, username: str, password: str, previous_token: str | None):
        with self.db.transaction() as connection:
            row = connection.execute('SELECT * FROM users WHERE lower(username)=?', (username.strip().lower(),)).fetchone()
            verified = verify_password(password, row['password_hash'] if row else self.dummy_hash)
            if not row or not verified:
                fail(ErrorCode.UNAUTHENTICATED, '用户名或密码错误。')
            now = int(time.time())
            connection.execute('DELETE FROM sessions WHERE expires_at<=?', (now,))
            if previous_token:
                connection.execute('DELETE FROM sessions WHERE token_hash=?', (digest(previous_token),))
            token = secrets.token_urlsafe(32)
            csrf = self.csrf_for(token)
            connection.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest(token), row['id'], digest(csrf), now + self.session_seconds))
            return User(row['id'], row['username'], row['display_name'], row['role']), token, csrf

    def authenticate(self, token: str | None, csrf: str | None = None, *, write=False):
        if not token or len(token) > 128:
            fail(ErrorCode.UNAUTHENTICATED, '请先登录。')
        with self.db.transaction(write=False) as connection:
            row = connection.execute('SELECT u.*,s.csrf_hash FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?', (digest(token), int(time.time()))).fetchone()
            if not row:
                fail(ErrorCode.UNAUTHENTICATED, '登录已过期，请重新登录。')
            if write and (not csrf or not hmac.compare_digest(row['csrf_hash'], digest(csrf))):
                fail(ErrorCode.FORBIDDEN, '请求验证失败，请刷新后重试。')
            return User(row['id'], row['username'], row['display_name'], row['role'])

    @staticmethod
    def csrf_for(token: str):
        # The token stays in an HttpOnly cookie; the derived CSRF value is returned
        # only in same-origin authenticated responses. GET never rotates state.
        return digest('campmate-csrf:' + token)

    def logout(self, token: str):
        with self.db.transaction() as connection:
            connection.execute('DELETE FROM sessions WHERE token_hash=?', (digest(token),))


def require_role(user: User, role: str):
    if user.role != role:
        fail(ErrorCode.FORBIDDEN, '当前账户没有此操作权限。')
