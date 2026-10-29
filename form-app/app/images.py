from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

# 前端已經把照片縮到 1600px，正常請求遠低於這個值；直接打 API 的大圖或解壓縮炸彈在這裡擋掉。
# 3000 萬像素解碼後約 90MB，2GB 主機上同時幾個請求還撐得住
MAX_PIXELS = 30_000_000
MAX_DIM = 1600
JPEG_QUALITY = 85
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidImage(ValueError):
    pass


@dataclass
class Photo:
    data: bytes
    width: int
    height: int


def normalize(raw: bytes) -> Photo:
    """驗證是真的圖片，轉正、縮到 1600px、重新編碼成 JPEG。

    重新編碼會丟掉 EXIF（含 GPS 位置）和圖片裡夾帶的其他資料。
    """
    try:
        with Image.open(BytesIO(raw)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise InvalidImage(f"format {probe.format}")
            if probe.width * probe.height > MAX_PIXELS:
                raise InvalidImage("too many pixels")
            probe.verify()
        with Image.open(BytesIO(raw)) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((MAX_DIM, MAX_DIM))
            out = BytesIO()
            im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return Photo(out.getvalue(), im.width, im.height)
    except InvalidImage:
        raise
    except Exception as exc:  # Pillow 對壞檔會丟各種例外
        raise InvalidImage(type(exc).__name__) from exc
