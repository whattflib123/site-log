import os
import tempfile
from io import BytesIO

import pytest
from PIL import Image

# app.main 在 import 時讀設定，所以要在 import 前設好環境變數
os.environ.update({
    "WEBDAV_URL": "http://dav.test/dav",
    "WEBDAV_USER": "bot@example.com",
    "WEBDAV_PASSWORD": "secret",
    "UPLOAD_ROOT": "/",
    "RATE_LIMIT": "5/minute",
    "UPLOAD_PIN": "2468",
    "TURNSTILE_SITE_KEY": "1x00000000000000000000AA",
    "TURNSTILE_SECRET": "1x0000000000000000000000000000000AA",
    "TURNSTILE_HOSTNAME": "form.example.com",
    "ACCESS_TEAM_DOMAIN": "team.example.com",
    "ACCESS_AUD": "aud-123",
    "ADMIN_EMAILS": "Boss@example.com",
    "CF_ACCOUNT_ID": "acct",
    "CF_LIST_ID": "list1",
    "CF_API_TOKEN": "cf-token",
    "CF_DRIVE_LIST_ID": "drive1",
    "DRIVE_SHARE_URL": "https://drive.example.com/s/abc",
    "PROJECTS_FILE": os.path.join(tempfile.mkdtemp(prefix="sitelog-test-"), "projects.json"),
})


def jpeg_bytes(size=(800, 600), color=(200, 80, 40), exif=None) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG", exif=exif or b"")
    return out.getvalue()


@pytest.fixture
def jpeg():
    return jpeg_bytes
