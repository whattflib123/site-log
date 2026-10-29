from io import BytesIO

import pytest
from PIL import Image

from app.images import InvalidImage, normalize


def test_jpeg_is_reencoded(jpeg):
    photo = normalize(jpeg((800, 600)))
    assert (photo.width, photo.height) == (800, 600)
    with Image.open(BytesIO(photo.data)) as im:
        assert im.format == "JPEG"


def test_large_photo_is_downscaled(jpeg):
    photo = normalize(jpeg((4000, 3000)))
    assert (photo.width, photo.height) == (1600, 1200)


def test_exif_and_gps_are_removed(jpeg):
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x8825] = {2: (23.0, 30.0, 0.0)}  # GPSInfo: 緯度
    photo = normalize(jpeg(exif=exif.tobytes()))
    with Image.open(BytesIO(photo.data)) as im:
        assert len(im.getexif()) == 0


def test_exif_orientation_is_applied(jpeg):
    exif = Image.Exif()
    exif[0x0112] = 6  # 需要順時針轉 90 度
    photo = normalize(jpeg((800, 600), exif=exif.tobytes()))
    assert (photo.width, photo.height) == (600, 800)


def test_png_with_alpha_becomes_rgb_jpeg():
    out = BytesIO()
    Image.new("RGBA", (300, 200), (0, 0, 0, 0)).save(out, "PNG")
    photo = normalize(out.getvalue())
    with Image.open(BytesIO(photo.data)) as im:
        assert im.mode == "RGB"


@pytest.mark.parametrize("raw", [
    b"",
    b"not an image at all",
    b"PK\x03\x04" + b"\x00" * 100,  # zip / docx
    b"\xff\xd8\xff\xe0" + b"\x00" * 50,  # 壞掉的 JPEG
])
def test_garbage_is_rejected(raw):
    with pytest.raises(InvalidImage):
        normalize(raw)


def test_gif_is_rejected():
    out = BytesIO()
    Image.new("P", (10, 10)).save(out, "GIF")
    with pytest.raises(InvalidImage):
        normalize(out.getvalue())


def test_pixel_bomb_is_rejected():
    out = BytesIO()
    Image.new("1", (9000, 9000)).save(out, "PNG")  # 81MP，檔案很小
    with pytest.raises(InvalidImage):
        normalize(out.getvalue())
