from io import BytesIO
from pathlib import Path

from docx.shared import Pt
from docxtpl import DocxTemplate, InlineImage, Listing

from .images import Photo
from .schemas import Submission

TEMPLATE = Path(__file__).parent / "doc_templates" / "template.docx"

# 照片欄寬 6554 twips ≈ 327.7pt，左右各留 8pt；高度上限和舊版前端一致
PHOTO_MAX_W_PT = 6554 / 20 - 16
PHOTO_MAX_H_PT = 220


def _photo_size(photo: Photo) -> tuple[Pt, Pt]:
    scale = min(PHOTO_MAX_W_PT / photo.width, PHOTO_MAX_H_PT / photo.height, 1)
    return Pt(photo.width * scale), Pt(photo.height * scale)


def render(sub: Submission, photos: list[Photo], template: Path = TEMPLATE) -> bytes:
    """用 template.docx 產生 Word，全程在記憶體裡，不寫入檔案系統。"""
    tpl = DocxTemplate(template)
    entries = []
    for entry, photo in zip(sub.entries, photos, strict=True):
        width, height = _photo_size(photo)
        lines = [line.strip() for line in entry.desc.splitlines() if line.strip()]
        entries.append({
            "date": entry.date.strftime("%Y/%m/%d") if entry.date else "",
            "item": entry.item,
            "location": entry.location,
            "desc": Listing("\n".join(lines)),
            "photo": InlineImage(tpl, BytesIO(photo.data), width=width, height=height),
        })
    tpl.render({
        "doc_title": sub.doc_title,
        "project_title": sub.project_title,
        "code": sub.code,
        "entries": entries,
    }, autoescape=True)
    out = BytesIO()
    tpl.save(out)
    return out.getvalue()
