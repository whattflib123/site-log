"""從 form-app 容器內測「表單存檔」整條路：WebDAV 寫入 → Cloudreve → R2，再讀回、刪掉。

healthcheck.sh 每小時跑一次：
  docker compose exec -T form-app python - < scripts/check_storage.py
成功印 ok，失敗印 fail: 原因（結束碼 1）。不印帳密。
"""
import sys
import time

import httpx

from app.settings import get_settings

s = get_settings()
url = s.webdav_url.rstrip("/") + "/_healthcheck.txt"
body = f"sitelog healthcheck {time.time():.0f}".encode()

with httpx.Client(auth=(s.webdav_user, s.webdav_password), timeout=30) as dav:
    try:
        put = dav.put(url, content=body)
        if put.status_code not in (200, 201, 204):
            print(f"fail: 寫入 HTTP {put.status_code}")
            sys.exit(1)
        get = dav.get(url)
        if get.is_redirect:
            # R2 預簽章網址不能帶 Basic auth，另外開一個沒有帳密的連線去拿
            get = httpx.get(get.headers["location"], timeout=30)
        if get.status_code != 200 or get.content != body:
            print(f"fail: 讀回 HTTP {get.status_code}")
            sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"fail: 連線錯誤 {type(exc).__name__}")
        sys.exit(1)
    finally:
        try:
            dav.delete(url)
        except httpx.HTTPError:
            pass
print("ok")
