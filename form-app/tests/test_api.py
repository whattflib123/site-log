import json
import re
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import main
from app.security import SITEVERIFY_URL
from app.storage import UploadError

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def access_token(key=KEY, aud="aud-123", iss="https://team.example.com", exp_in=300, email="worker@example.com"):
    now = int(time.time())
    return jwt.encode({"aud": aud, "iss": iss, "email": email, "iat": now, "exp": now + exp_in}, key, algorithm="RS256")


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    # Access 公鑰：不連網，直接給測試用的公鑰
    monkeypatch.setattr(main.require_access, "jwks",
                        SimpleNamespace(get_signing_key_from_jwt=lambda t: SimpleNamespace(key=KEY.public_key())))
    main.limiter.reset()
    # 送出時工程要在管理者的清單裡（test_projects 會自己清空這個檔）
    Path(main.settings.projects_file).write_text(json.dumps([{"id": "s1", "name": "工程一", "title": ""}]), encoding="utf-8")
    saved = []
    monkeypatch.setattr(main.WebDAVStorage, "save",
                        lambda self, folder, name, data, *rest: saved.append((folder, name, data)) or "/" + "/".join(folder + [name]))
    with respx.mock(assert_all_called=False) as router:
        router.route(host="testserver").pass_through()
        router.post(SITEVERIFY_URL).respond(json={"success": True, "action": "submit", "hostname": "form.example.com"})
        yield SimpleNamespace(saved=saved, router=router)


@pytest.fixture
def client():
    return TestClient(main.app, headers={"Cf-Access-Jwt-Assertion": access_token()})


def form_data(**overrides):
    data = {
        "category": "photo",
        "project_name": "工程一",
        "project_title": "河濱公園環境改善",
        "code": "JT-026",
        "filename": "工審-026",
        "pin": "2468",
        "cf-turnstile-response": "token-ok",
        "entries": json.dumps([{"date": "2026-10-28", "item": "鋼筋", "location": "座椅", "desc": "主筋"}]),
    }
    data.update(overrides)
    return data


def post(client, jpeg, n_photos=1, files=None, **overrides):
    files = files if files is not None else [("photos", (f"p{i}.jpg", jpeg(), "image/jpeg")) for i in range(n_photos)]
    return client.post("/submit", data=form_data(**overrides), files=files)


# ---------- 頁面 ----------

def test_index_has_matching_csp_nonce(client):
    res = client.get("/")
    assert res.status_code == 200
    nonce = re.search(r"script-src 'nonce-([^']+)'", res.headers["content-security-policy"]).group(1)
    scripts = re.findall(r"<script([^>]*)>", res.text)
    assert scripts and all(f'nonce="{nonce}"' in attrs for attrs in scripts)
    assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
    assert '"1x00000000000000000000AA"' in res.text  # Turnstile site key 注入
    assert "docx = {}" not in res.text  # 前端不再內嵌 docx 函式庫


def test_index_nonce_changes_per_request(client):
    a = client.get("/").headers["content-security-policy"]
    b = client.get("/").headers["content-security-policy"]
    assert a != b


def test_healthz_needs_no_login():
    assert TestClient(main.app).get("/healthz").json() == {"ok": True}


# ---------- Cloudflare Access ----------

@pytest.mark.parametrize("headers", [
    {},
    {"Cf-Access-Jwt-Assertion": "garbage"},
    {"Cf-Access-Jwt-Assertion": access_token(key=OTHER_KEY)},
    {"Cf-Access-Jwt-Assertion": access_token(aud="other-app")},
    {"Cf-Access-Jwt-Assertion": access_token(iss="https://evil.example.com")},
    {"Cf-Access-Jwt-Assertion": access_token(exp_in=-60)},
])
def test_access_jwt_required(headers, jpeg):
    c = TestClient(main.app, headers=headers)
    assert c.get("/").status_code == 403
    assert post(c, jpeg).status_code == 403


def test_hs256_token_rejected(jpeg):
    # 演算法混淆攻擊：用公鑰當 HMAC 密鑰簽
    forged = jwt.encode({"aud": "aud-123", "iss": "https://team.example.com", "exp": int(time.time()) + 60},
                        "anything", algorithm="HS256")
    assert TestClient(main.app, headers={"Cf-Access-Jwt-Assertion": forged}).get("/").status_code == 403


# ---------- 送出 ----------

def test_submit_success(client, jpeg, setup):
    res = post(client, jpeg)
    assert res.status_code == 200, res.text
    assert res.content[:4] == b"PK\x03\x04"
    assert res.headers["content-type"].startswith("application/vnd.openxmlformats")
    name = unquote(res.headers["x-saved-as"])
    assert re.fullmatch(r"\d{8}-\d{6}_工程一_施工照片_工審-026\.docx", name)
    folder, saved_name, data = setup.saved[0]
    assert re.fullmatch(r"\d{4}", folder[0]) and re.fullmatch(r"\d{2}", folder[1])
    assert saved_name == name and data == res.content
    assert "filename*=UTF-8''" in res.headers["content-disposition"]


def test_turnstile_token_and_ip_sent(client, jpeg, setup):
    post(client, jpeg)
    sent = setup.router.calls.last.request.content.decode()
    assert "response=token-ok" in sent and "secret=" in sent and "idempotency_key=" in sent


@pytest.mark.parametrize("verdict", [
    {"success": False, "error-codes": ["invalid-input-response"]},
    {"success": True, "action": "other", "hostname": "form.example.com"},
    {"success": True, "action": "submit", "hostname": "evil.example.com"},
])
def test_turnstile_rejections(client, jpeg, setup, verdict):
    setup.router.post(SITEVERIFY_URL).respond(json=verdict)
    res = post(client, jpeg)
    assert res.status_code == 403 and "人機驗證" in res.json()["detail"]
    assert setup.saved == []


def test_turnstile_testing_key_skips_action_check(client, jpeg, setup):
    # Cloudflare 測試金鑰的實際回應（2026-10-28 實測）：沒有 action，hostname 是 example.com
    setup.router.post(SITEVERIFY_URL).respond(json={
        "success": True, "error-codes": [], "hostname": "example.com",
        "metadata": {"result_with_testing_key": True}})
    assert post(client, jpeg).status_code == 200


def test_missing_turnstile_token(client, jpeg):
    assert post(client, jpeg, **{"cf-turnstile-response": ""}).status_code == 403


def test_turnstile_unreachable_fails_closed(client, jpeg, setup):
    setup.router.post(SITEVERIFY_URL).mock(side_effect=httpx.ConnectError("down"))
    assert post(client, jpeg).status_code == 403


def test_wrong_pin(client, jpeg):
    res = post(client, jpeg, pin="0000")
    assert res.status_code == 403 and res.json()["detail"] == "上傳代碼不正確"


@pytest.mark.parametrize("overrides, message", [
    ({"filename": ""}, "檔案名稱必填"),
    ({"category": "nope"}, "表單類別格式不正確"),
    ({"entries": json.dumps([{"desc": "長" * 2001}])}, "第 1 筆的說明太長（最多 2000 字）"),
    ({"entries": json.dumps([{"date": "not-a-date"}])}, "第 1 筆的日期格式不正確"),
    ({"entries": json.dumps([{"evil": 1}])}, "第 1 筆的evil格式不正確"),
    ({"entries": "[]"}, "請至少新增一筆照片資料"),
    ({"entries": "{not json"}, "資料格式不正確，請重新整理頁面後再試"),
    ({"code": "x" * 61}, "編號太長（最多 60 字）"),
])
def test_validation_errors(client, jpeg, setup, overrides, message):
    res = post(client, jpeg, **overrides)
    assert res.status_code == 422
    assert res.json()["detail"] == message
    assert setup.saved == []


def test_photo_count_must_match(client, jpeg):
    res = post(client, jpeg, n_photos=2)
    assert res.status_code == 422 and res.json()["detail"] == "每一筆都要有照片"


def test_bad_photo(client, jpeg):
    res = post(client, jpeg, files=[("photos", ("x.jpg", b"<?php evil(); ?>", "image/jpeg"))])
    assert res.status_code == 422 and res.json()["detail"] == "第 1 筆的照片無法讀取，請換一張"


def test_too_many_photos(client, jpeg):
    entries = json.dumps([{}] * 31)
    files = [("photos", (f"p{i}.jpg", b"x", "image/jpeg")) for i in range(31)]
    assert post(client, jpeg, files=files, entries=entries).status_code in (400, 422)


def test_body_size_limit(client):
    res = client.post("/submit", content=b"x", headers={"Content-Length": str(61 * 1024 * 1024)})
    assert res.status_code == 413


def test_storage_failure_is_friendly(client, jpeg, monkeypatch):
    def boom(self, *a):
        raise UploadError("PUT HTTP 500 at http://cloudreve:5212/dav/secret")
    monkeypatch.setattr(main.WebDAVStorage, "save", boom)
    res = post(client, jpeg)
    assert res.status_code == 502
    assert "cloudreve" not in res.text and "500" not in res.text
    assert "網盤" in res.json()["detail"]


def test_rate_limit(client, jpeg):
    codes = [post(client, jpeg).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429


def test_rate_limit_counts_failed_attempts(client, jpeg):
    codes = [post(client, jpeg, pin="0000").status_code for _ in range(6)]
    assert codes[5] == 429


def test_submit_rejects_unknown_project(client, jpeg, setup):
    res = post(client, jpeg, project_name="自己亂加的工程")
    assert res.status_code == 422 and "不在工程清單" in res.json()["detail"]
    assert setup.saved == []


def test_submit_when_project_list_broken(client, jpeg, setup):
    Path(main.settings.projects_file).write_text("{broken", encoding="utf-8")
    assert post(client, jpeg).status_code == 503
    assert setup.saved == []


def test_errors_have_english(client, jpeg, setup):
    # 表單頁切英文時顯示 detail_en
    body = post(client, jpeg, pin="0000").json()
    assert body["detail"] == "上傳代碼不正確" and body["detail_en"] == "Wrong upload code"
    entries = json.dumps([{"item": "x" * 101}])
    body = post(client, jpeg, entries=entries).json()
    assert body["detail"] == "第 1 筆的項目太長（最多 100 字）"
    assert body["detail_en"] == "Record 1: Item is too long (max 100 characters)"
    assert body["detail_vi"] == "Mục 1: Hạng mục quá dài (tối đa 100 ký tự)"
    assert body["detail_th"] == "รายการที่ 1: รายการยาวเกินไป (ไม่เกิน 100 ตัวอักษร)"


def test_every_message_has_all_languages():
    from app import messages
    for key, texts in messages.MESSAGES.items():
        assert set(texts) == set(messages.LANGS), key
    for lang in messages.LANGS:
        assert set(messages.FIELD_LABELS[lang]) == set(messages.FIELD_LABELS["zh"]), lang
