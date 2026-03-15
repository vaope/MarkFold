from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from markfold.config import get_settings


class FeishuApiError(RuntimeError):
    pass


@dataclass
class DownloadedResource:
    filename: str
    content_type: str
    content: bytes


@dataclass
class FeishuWsConnectConfig:
    url: str
    service_id: int
    device_id: str
    ping_interval_ms: int
    reconnect_count: int
    reconnect_interval_ms: int
    reconnect_nonce_ms: int


class FeishuClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        base_url: str = "https://open.feishu.cn",
        timeout: float = 20.0,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._tenant_access_token: str | None = None
        self._tenant_access_token_expires_at = 0.0

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        json_body: dict | None = None,
    ) -> dict:
        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code", 0) != 0:
            raise FeishuApiError(payload.get("msg") or payload.get("message") or "Feishu API request failed")
        return payload

    def _get_tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_access_token and now < self._tenant_access_token_expires_at - 60:
            return self._tenant_access_token

        payload = self._request_json(
            "POST",
            "/open-apis/auth/v3/tenant_access_token/internal",
            json_body={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
        )
        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuApiError("Feishu tenant_access_token missing in auth response")
        expires_in = int(payload.get("expire", 7200))
        self._tenant_access_token = token
        self._tenant_access_token_expires_at = now + expires_in
        return token

    def _authorized_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_tenant_access_token()}"}

    def get_ws_connect_config(self) -> FeishuWsConnectConfig:
        payload = self._request_json(
            "POST",
            "/callback/ws/endpoint",
            headers={"locale": "zh"},
            json_body={
                "AppID": self.app_id,
                "AppSecret": self.app_secret,
            },
        )
        data = payload.get("data", {})
        url = data.get("URL")
        client_config = data.get("ClientConfig", {})
        if not url:
            raise FeishuApiError("Feishu WS connect URL missing in response")

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        device_id = query.get("device_id", [""])[0]
        service_id = int(query.get("service_id", ["0"])[0] or 0)
        if not device_id or not service_id:
            raise FeishuApiError("Feishu WS connect config missing device_id or service_id")

        return FeishuWsConnectConfig(
            url=url,
            service_id=service_id,
            device_id=device_id,
            ping_interval_ms=int(client_config.get("PingInterval", 120)) * 1000,
            reconnect_count=int(client_config.get("ReconnectCount", -1)),
            reconnect_interval_ms=int(client_config.get("ReconnectInterval", 120)) * 1000,
            reconnect_nonce_ms=int(client_config.get("ReconnectNonce", 30)) * 1000,
        )

    def send_text_message(self, receive_id: str, text: str, *, receive_id_type: str = "chat_id") -> dict:
        return self._request_json(
            "POST",
            "/open-apis/im/v1/messages",
            headers=self._authorized_headers(),
            params={"receive_id_type": receive_id_type},
            json_body={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )

    def download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str,
        fallback_filename: str | None = None,
    ) -> DownloadedResource:
        response = httpx.get(
            f"{self.base_url}/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
            headers=self._authorized_headers(),
            params={"type": resource_type},
            timeout=self.timeout,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "application/octet-stream")
        if content_type.startswith("application/json"):
            payload = response.json()
            raise FeishuApiError(payload.get("msg") or "Feishu resource download failed")
        filename = _extract_filename(response.headers.get("content-disposition")) or fallback_filename
        if not filename:
            filename = _default_filename(file_key, resource_type, content_type)
        return DownloadedResource(
            filename=filename,
            content_type=content_type,
            content=response.content,
        )


def _extract_filename(content_disposition: str | None) -> str | None:
    if not content_disposition:
        return None
    match = re.search(r"filename\\*=UTF-8''([^;]+)", content_disposition, re.IGNORECASE)
    if match:
        return os.path.basename(unquote(match.group(1)))
    match = re.search(r'filename="?([^\";]+)"?', content_disposition, re.IGNORECASE)
    if match:
        return os.path.basename(match.group(1))
    return None


def _default_filename(file_key: str, resource_type: str, content_type: str) -> str:
    ext = ""
    if resource_type == "image":
        ext = ".png"
    elif "/" in content_type:
        ext = f".{content_type.split('/', 1)[1].split(';', 1)[0]}"
    return f"{file_key}{ext}"


@lru_cache(maxsize=1)
def get_feishu_client() -> FeishuClient:
    settings = get_settings()
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise ValueError("Feishu integration is not configured. Set MARKFOLD_FEISHU_APP_ID and MARKFOLD_FEISHU_APP_SECRET.")
    return FeishuClient(
        app_id=settings.feishu_app_id,
        app_secret=settings.feishu_app_secret.get_secret_value(),
        base_url=settings.feishu_base_url,
    )
