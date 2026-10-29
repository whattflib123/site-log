import hmac
import logging
import uuid
from typing import Optional

import httpx
import jwt
from fastapi import HTTPException, Request

from .settings import Settings

log = logging.getLogger("form-app.security")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_ACTION = "submit"
MAX_TOKEN_LEN = 2048


def check_pin(settings: Settings, pin: str) -> bool:
    if not settings.upload_pin:
        return True
    return hmac.compare_digest(pin.encode(), settings.upload_pin.encode())


def verify_turnstile(settings: Settings, token: str, remote_ip: Optional[str],
                     client: Optional[httpx.Client] = None) -> bool:
    """伺服器端驗證 Turnstile token。token 只能用一次、5 分鐘內有效。"""
    if not settings.turnstile_enabled:
        return True
    if not token or len(token) > MAX_TOKEN_LEN:
        return False
    data = {"secret": settings.turnstile_secret, "response": token, "idempotency_key": str(uuid.uuid4())}
    if remote_ip:
        data["remoteip"] = remote_ip
    own_client = client is None
    client = client or httpx.Client(timeout=10)
    try:
        # 同一個 idempotency_key 可以安全重試一次
        for attempt in range(2):
            try:
                result = client.post(SITEVERIFY_URL, data=data).json()
                break
            except (httpx.TransportError, ValueError) as exc:
                if attempt == 1:
                    log.error("turnstile siteverify unreachable: %s", exc)
                    return False
    finally:
        if own_client:
            client.close()

    if not result.get("success"):
        log.warning("turnstile rejected: %s", result.get("error-codes"))
        return False
    if (result.get("metadata") or {}).get("result_with_testing_key"):
        # Cloudflare 測試金鑰不回 action、hostname 固定是 example.com；只有 secret 設成測試金鑰才會走到這裡
        log.warning("turnstile 使用測試金鑰，略過 action/hostname 檢查（只適合本機）")
        return True
    if result.get("action") != TURNSTILE_ACTION:
        log.warning("turnstile action mismatch: %r", result.get("action"))
        return False
    if settings.turnstile_hostname and result.get("hostname") != settings.turnstile_hostname:
        log.warning("turnstile hostname mismatch: %r", result.get("hostname"))
        return False
    return True


class AccessVerifier:
    """驗證 Cloudflare Access 加在請求上的 JWT，避免有人繞過 Cloudflare 直接打主機 IP。"""

    def __init__(self, settings: Settings):
        self.enabled = settings.access_enabled
        if self.enabled:
            self.aud = settings.access_aud
            self.issuer = f"https://{settings.access_team_domain}"
            # 公鑰快取 10 分鐘
            self.jwks = jwt.PyJWKClient(f"{self.issuer}/cdn-cgi/access/certs", cache_keys=True, lifespan=600)

    def __call__(self, request: Request) -> str:
        """FastAPI dependency；回傳登入的 email（未啟用時回空字串）。"""
        if not self.enabled:
            return ""
        token = request.headers.get("cf-access-jwt-assertion", "")
        if not token:
            raise HTTPException(403, "請先登入 / Please sign in")
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            payload = jwt.decode(token, key.key, algorithms=["RS256"], audience=self.aud, issuer=self.issuer)
        except jwt.PyJWTError as exc:
            log.warning("access jwt rejected: %s", type(exc).__name__)
            raise HTTPException(403, "登入已失效，請重新整理頁面 / Session expired, please reload the page") from exc
        return payload.get("email", "")
