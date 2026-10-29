import re
import unicodedata
from datetime import datetime

# Windows 不允許的字元、路徑分隔、URL 會出問題的 # %，以及控制字元
_UNSAFE = re.compile(r'[\\/:*?"<>|#%\x00-\x1f\x7f]')
_SPACES = re.compile(r"\s+")
_MAX_PART = 60


def clean_part(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    # 去掉 Unicode 格式字元（零寬、雙向控制），避免檔名顯示和實際不同
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = _SPACES.sub(" ", text)
    text = _UNSAFE.sub("_", text).strip(" .")
    return text[:_MAX_PART].strip(" .")


def build_filename(now: datetime, *parts: str) -> str:
    """{YYYYMMDD-HHMMSS}_{部分1}_{部分2}….docx，空的部分略過。"""
    cleaned = [p for p in (clean_part(x) for x in parts) if p]
    stem = "_".join([now.strftime("%Y%m%d-%H%M%S"), *cleaned]) if cleaned else now.strftime("%Y%m%d-%H%M%S") + "_未命名"
    return stem + ".docx"


def numbered(filename: str, n: int) -> str:
    """同名時改成 檔名-2.docx、檔名-3.docx…"""
    stem, dot, ext = filename.rpartition(".")
    return f"{stem}-{n}.{ext}" if dot else f"{filename}-{n}"
