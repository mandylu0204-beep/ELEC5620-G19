"""Bounded asynchronous Chat Completions client for the ELEC5620 proxy."""
import asyncio
from dataclasses import dataclass
import json

import httpx

from ..contracts.enums import AllowedAction, ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from .config import CampusModelSettings

CLIENT_VERSION = 'b04-campus-client-1'
MAX_RESPONSE_BYTES = 262144
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def model_failure(message, *, recoverable=False, code=ErrorCode.AGENT_FAILURE, status=None):
    return ContractFailure(ContractError(
        code=code, message=message, recoverable=recoverable,
        allowed_actions=[AllowedAction.RETRY] if recoverable else [
            AllowedAction.EDIT_INPUT if code == ErrorCode.REQUEST_NOT_CONFIRMED else AllowedAction.CONTACT_OPERATOR],
        context={'component': 'campus_model', **({'http_status': str(status)} if status else {})},
    ))


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON value')))


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    attempts: int
    usage: dict[str, int]
    served_model: str | None = None


class CampusModelClient:
    """No redirects, environment proxy, SDK auto-retries, or fallback provider."""
    def __init__(self, settings: CampusModelSettings, *, transport=None):
        self.settings, self.transport = settings, transport

    @property
    def identity(self):
        return {'client_version': CLIENT_VERSION, **self.settings.public_identity()}

    def validate_configuration(self):
        """Offline readiness check; does not send a billable health/probe call."""
        key = self.settings.api_key.get_secret_value().strip()
        if (not key or any(word in key.upper() for word in ('REPLACE_WITH', 'YOUR_KEY'))
                or any(not 33 <= ord(character) <= 126 for character in key)):
            raise model_failure('校园模型密钥未配置或无效；请仅在本地配置 ELEC5620_API_KEY。')

    async def complete(self, messages):
        self.validate_configuration()
        key = self.settings.api_key.get_secret_value().strip()
        if (not messages or any(not isinstance(message, dict)
                or set(message) != {'role', 'content'}
                or message['role'] not in {'system', 'user', 'assistant'}
                or not isinstance(message['content'], str) for message in messages)):
            raise model_failure('模型消息不符合受控聊天协议。', code=ErrorCode.CONTRACT_INVALID)
        if any(key in message['content'] for message in messages):
            raise model_failure('模型上下文包含密钥；请求已阻止。', code=ErrorCode.CONTRACT_INVALID)
        payload = {'model': self.settings.model, 'messages': messages,
            'max_completion_tokens': self.settings.max_completion_tokens, 'stream': False}
        if self.settings.reasoning_effort is not None:
            payload['reasoning_effort'] = self.settings.reasoning_effort
        try:
            size = len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        except (ValueError, UnicodeError):
            raise model_failure('模型请求包含无法编码的数据。', code=ErrorCode.CONTRACT_INVALID) from None
        if size > 131072:
            raise model_failure('模型请求超过受控大小限制。', code=ErrorCode.CONTRACT_INVALID)
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, trust_env=False,
                follow_redirects=False, transport=self.transport) as client:
            for attempt in range(1, self.settings.max_attempts + 1):
                retry = False
                try:
                    async with client.stream('POST', self.settings.base_url + '/chat/completions',
                            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                            json=payload) as response:
                        status = response.status_code
                        if status in RETRYABLE_STATUS:
                            if attempt == self.settings.max_attempts:
                                raise model_failure('校园模型暂时不可用或限流；请稍后重试。',
                                    recoverable=True, status=status)
                            retry = True
                        elif not 200 <= status < 300:
                            # Never include proxy body, request headers or exception text.
                            raise model_failure('校园模型请求被拒绝；请检查密钥、VPN 和代理配置。', status=status)
                        else:
                            chunks, size = [], 0
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > MAX_RESPONSE_BYTES:
                                    raise model_failure('校园模型响应超过受控大小限制。',
                                        code=ErrorCode.CONTRACT_INVALID)
                                chunks.append(chunk)
                            return self._completion(b''.join(chunks), attempt)
                except httpx.HTTPError:
                    if attempt == self.settings.max_attempts:
                        raise model_failure('校园模型网络请求失败；请检查校园网络/VPN 后重试。',
                            recoverable=True) from None
                    retry = True
                if retry:
                    await asyncio.sleep(0.25 * attempt)
        raise model_failure('校园模型未返回可用结果。', recoverable=True)

    def _completion(self, payload, attempt):
        try:
            data = strict_json(payload)
            choices = data['choices']
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError('Expected one choice')
            choice = choices[0]
            message = choice['message']
            content = message['content']
            if (not isinstance(content, str) or not content.strip()
                    or choice.get('finish_reason') not in {None, 'stop'}
                    or message.get('tool_calls') or message.get('function_call') or message.get('refusal')
                    or message.get('role') not in {None, 'assistant'}):
                raise ValueError('Empty, truncated, incompatible or refused completion')
            served_model = data.get('model')
            if served_model is not None and (not isinstance(served_model, str) or not 1 <= len(served_model) <= 200):
                raise ValueError('Invalid served model identity')
            key = self.settings.api_key.get_secret_value().strip()
            if key in content or (served_model and key in served_model):
                raise ValueError('Proxy echoed a credential')
            usage = {}
            for name, value in (data.get('usage') or {}).items():
                if name in {'prompt_tokens', 'completion_tokens', 'total_tokens'}:
                    if type(value) is not int or value < 0:
                        raise ValueError('Invalid usage')
                    usage[name] = value
            return Completion(content, self.settings.model, attempt, usage, served_model)
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
            raise model_failure('校园模型响应格式无效或被截断；未采纳任何输出。',
                code=ErrorCode.CONTRACT_INVALID) from None
