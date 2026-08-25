from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def parse_mcp_payload(raw: Any) -> dict[str, Any]:
    value = _decode_json(raw)
    for _ in range(6):
        if not isinstance(value, dict):
            break
        if value.get("error"):
            raise RuntimeError(str(value["error"]))
        if "uuid" in value and "status" in value:
            break
        if isinstance(value.get("structuredContent"), dict):
            value = value["structuredContent"]
            continue
        if "result" in value:
            candidate = _decode_json(value["result"])
            if candidate is value:
                break
            value = candidate
            continue
        break
    if not isinstance(value, dict):
        raise RuntimeError("MCP Tool 未返回 JSON 对象")
    return value


class HermesSessionClient:
    def __init__(self, api_url: str, api_key: str, timeout: float = 120):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def inject(self, session_id: str, message: str) -> None:
        if not self.api_key:
            raise RuntimeError("API_SERVER_KEY 未配置")
        url = f"{self.api_url}/api/sessions/{quote(session_id, safe='')}/chat"
        request = Request(
            url,
            data=json.dumps({"message": message}, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Hermes Session API 返回 HTTP {response.status}")
                response.read()
        except HTTPError as exc:
            raise RuntimeError(f"Hermes Session API 返回 HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"Hermes Session API 不可用：{exc.reason}") from exc
