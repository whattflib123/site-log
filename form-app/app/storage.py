import logging
import time
from typing import Callable, Optional
from urllib.parse import quote

import httpx

from .naming import numbered
from .settings import Settings

log = logging.getLogger("form-app.storage")

RETRIES = 3  # 第一次失敗後最多再試 3 次，間隔 1s、2s、4s
MAX_SAME_NAME = 50
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UploadError(Exception):
    pass


class _Retryable(Exception):
    pass


class WebDAVStorage:
    """經 Cloudreve WebDAV 存檔。不可以繞過 Cloudreve 直接寫 bucket，否則網盤看不到檔案。"""

    def __init__(self, settings: Settings, client: Optional[httpx.Client] = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.base = settings.webdav_url.rstrip("/")
        self.root = [p for p in settings.upload_root.split("/") if p]
        self.client = client or httpx.Client(
            auth=(settings.webdav_user, settings.webdav_password),
            timeout=settings.webdav_timeout,
        )
        self.sleep = sleep

    def _url(self, parts: list[str]) -> str:
        return self.base + "/" + "/".join(quote(p, safe="") for p in parts)

    def _request(self, method: str, parts: list[str], ok: set[int], **kwargs) -> int:
        url = self._url(parts)
        for attempt in range(RETRIES + 1):
            try:
                res = self.client.request(method, url, **kwargs)
                if res.status_code >= 500 or res.status_code in (423, 429):
                    raise _Retryable(f"HTTP {res.status_code}")
                if res.status_code not in ok:
                    log.error("webdav %s %s -> HTTP %s", method, "/".join(parts), res.status_code)
                    raise UploadError(f"{method} HTTP {res.status_code}")
                return res.status_code
            except (httpx.TransportError, _Retryable) as exc:
                if attempt == RETRIES:
                    log.error("webdav %s %s failed after %d attempts: %s", method, "/".join(parts), attempt + 1, exc)
                    raise UploadError(f"{method} failed") from exc
                delay = 2 ** attempt
                log.warning("webdav %s %s attempt %d failed (%s), retry in %ss", method, "/".join(parts), attempt + 1, exc, delay)
                self.sleep(delay)
        raise AssertionError("unreachable")

    def ensure_dir(self, parts: list[str]) -> None:
        # 逐層 MKCOL；201 = 建立，405 = 已存在
        for i in range(1, len(parts) + 1):
            self._request("MKCOL", parts[:i], ok={201, 405})

    def save(self, folder: list[str], filename: str, data: bytes, content_type: str = DOCX_TYPE) -> str:
        """存到 {upload_root}/{folder…}/{filename}，同名自動改成 檔名-2.docx，回傳實際路徑。"""
        dir_parts = self.root + folder
        self.ensure_dir(dir_parts)
        for n in range(1, MAX_SAME_NAME + 1):
            name = filename if n == 1 else numbered(filename, n)
            # Cloudreve 的 WebDAV PUT 不支援 If-None-Match，只能先 HEAD 檢查
            if self._request("HEAD", dir_parts + [name], ok={200, 404}) == 404:
                self._request("PUT", dir_parts + [name], ok={200, 201, 204}, content=data,
                              headers={"Content-Type": content_type})
                return "/" + "/".join(dir_parts + [name])
        raise UploadError("too many files with the same name")
