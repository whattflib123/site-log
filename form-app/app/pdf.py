"""Word 轉 PDF：交給同一個 compose 內網的 Gotenberg（LibreOffice）。form-app 這邊全程在記憶體裡。"""
import logging
from typing import Optional

import httpx

from .settings import Settings

log = logging.getLogger("form-app.pdf")

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def convert(settings: Settings, docx: bytes, client: Optional[httpx.Client] = None) -> Optional[bytes]:
    """轉檔失敗回傳 None（呼叫端改給 Word），不讓 PDF 擋住整份表單。"""
    url = settings.gotenberg_url.rstrip("/") + "/forms/libreoffice/convert"
    own = client is None
    client = client or httpx.Client(timeout=settings.pdf_timeout)
    try:
        res = client.post(url, files={"files": ("document.docx", docx, DOCX_TYPE)})
        if res.status_code != 200 or not res.content.startswith(b"%PDF"):
            log.error("pdf convert -> HTTP %s", res.status_code)
            return None
        return res.content
    except httpx.HTTPError as exc:
        log.error("pdf convert failed: %s", type(exc).__name__)
        return None
    finally:
        if own:
            client.close()
