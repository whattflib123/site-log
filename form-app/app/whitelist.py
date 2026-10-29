"""表單白名單：Cloudflare Zero Trust 的 email 清單（Access 原則「外部人員」引用它）。"""
import logging
import re
from datetime import datetime
from typing import Optional

import httpx

from .settings import Settings

log = logging.getLogger("form-app.whitelist")

API = "https://api.cloudflare.com/client/v4"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")


class WhitelistError(Exception):
    pass


def normalize_email(raw: str) -> Optional[str]:
    email = raw.strip().replace("＠", "@").lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        return None
    return email


class Whitelist:
    def __init__(self, settings: Settings, client: Optional[httpx.Client] = None, list_id: str = ""):
        """預設是表單白名單；list_id 給網盤白名單用。"""
        self.account = settings.cf_account_id
        self.url = f"{API}/accounts/{self.account}/gateway/lists/{list_id or settings.cf_list_id}"
        self.client = client or httpx.Client(timeout=15, headers={"Authorization": f"Bearer {settings.cf_api_token}"})

    def _call(self, method: str, path: str = "", **kwargs) -> dict:
        try:
            r = self.client.request(method, self.url + path, **kwargs)
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.error("cloudflare list %s failed: %s", method, type(exc).__name__)
            raise WhitelistError from exc
        if not body.get("success"):
            log.error("cloudflare list %s rejected: %s", method, body.get("errors"))
            raise WhitelistError
        return body

    def items(self) -> list[dict]:
        out, page = [], 1
        while True:
            body = self._call("GET", "/items", params={"page": page, "per_page": 100})
            out += body.get("result") or []
            info = body.get("result_info") or {}
            if page * 100 >= info.get("total_count", 0):
                break
            page += 1
        return sorted(out, key=lambda i: i["value"])

    def add(self, email: str, by: str) -> None:
        note = f"{by} 於 {datetime.now():%Y-%m-%d %H:%M} 新增"
        self._call("PATCH", json={"append": [{"value": email, "description": note}]})

    def remove(self, email: str) -> None:
        self._call("PATCH", json={"remove": [email]})

    def revoke(self, email: str) -> None:
        """撤銷這個 email 在所有 Access 應用程式的登入，下次開頁面要重新驗證（就會被擋）。"""
        try:
            r = self.client.post(f"{API}/accounts/{self.account}/access/organizations/revoke_user", json={"email": email})
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.error("cloudflare revoke failed: %s", type(exc).__name__)
            raise WhitelistError from exc
        if not body.get("success"):
            log.error("cloudflare revoke rejected: %s", body.get("errors"))
            raise WhitelistError
