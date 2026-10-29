import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.whitelist import normalize_email

from test_api import access_token, setup  # noqa: F401  (autouse fixture：Access 公鑰、respx)

LIST_URL = "https://api.cloudflare.com/client/v4/accounts/acct/gateway/lists/list1"
DRIVE_LIST_URL = "https://api.cloudflare.com/client/v4/accounts/acct/gateway/lists/drive1"
REVOKE_URL = "https://api.cloudflare.com/client/v4/accounts/acct/access/organizations/revoke_user"
ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def admin():
    return TestClient(main.app, follow_redirects=False,
                      headers={"Cf-Access-Jwt-Assertion": access_token(email="boss@example.com")})


@pytest.fixture
def cf(setup):  # noqa: F811
    state = {"items": [{"value": "a@example.com", "created_at": "2026-10-28T00:00:00Z"}], "patches": [], "revoked": []}

    def items(request):
        return httpx.Response(200, json={"success": True, "result": state["items"],
                                         "result_info": {"total_count": len(state["items"])}})

    def patch(request):
        body = json.loads(request.content)
        state["patches"].append((body, request.headers["authorization"]))
        for i in body.get("append", []):
            state["items"].append({"value": i["value"], "created_at": "2026-10-28T00:00:00Z", "description": i["description"]})
        state["items"] = [i for i in state["items"] if i["value"] not in body.get("remove", [])]
        return httpx.Response(200, json={"success": True, "result": {}})

    setup.router.get(f"{LIST_URL}/items").mock(side_effect=items)
    setup.router.patch(LIST_URL).mock(side_effect=patch)
    # 網盤白名單：另一份清單，預設是空的
    state["drive"] = []

    def drive_items(request):
        return httpx.Response(200, json={"success": True, "result": state["drive"],
                                         "result_info": {"total_count": len(state["drive"])}})

    def drive_patch(request):
        body = json.loads(request.content)
        for i in body.get("append", []):
            state["drive"].append({"value": i["value"], "created_at": "2026-10-29T00:00:00Z", "description": i["description"]})
        state["drive"] = [i for i in state["drive"] if i["value"] not in body.get("remove", [])]
        return httpx.Response(200, json={"success": True, "result": {}})

    setup.router.get(f"{DRIVE_LIST_URL}/items").mock(side_effect=drive_items)
    setup.router.patch(DRIVE_LIST_URL).mock(side_effect=drive_patch)
    setup.router.post(REVOKE_URL).mock(side_effect=lambda r: state["revoked"].append(json.loads(r.content))
                                       or httpx.Response(200, json={"success": True, "result": True}))
    return state


def test_admin_page_lists_emails(admin, cf):
    r = admin.get("/admin")
    assert r.status_code == 200
    assert "a@example.com" in r.text
    assert "script-src" not in r.headers["content-security-policy"]  # 頁面沒有 script


def test_non_admin_forbidden(cf):
    worker = TestClient(main.app, headers={"Cf-Access-Jwt-Assertion": access_token(email="worker@example.com")})
    assert worker.get("/admin").status_code == 403
    assert worker.post("/admin/add", data={"email": "x@example.com"}, headers=ORIGIN).status_code == 403
    assert cf["patches"] == []


def test_admin_requires_login(cf):
    assert TestClient(main.app).get("/admin").status_code == 403


def test_add_and_remove(admin, cf):
    r = admin.post("/admin/add", data={"email": " New@Example.com "}, headers=ORIGIN)
    assert r.status_code == 303 and "msg=added" in r.headers["set-cookie"]
    body, auth = cf["patches"][-1]
    assert body["append"][0]["value"] == "new@example.com"
    assert "boss@example.com" in body["append"][0]["description"]
    assert auth == "Bearer cf-token"

    r = admin.post("/admin/remove", data={"email": "a@example.com"}, headers=ORIGIN)
    assert "msg=removed" in r.headers["set-cookie"]
    assert cf["patches"][-1][0] == {"remove": ["a@example.com"]}
    assert [i["value"] for i in cf["items"]] == ["new@example.com"]
    assert cf["revoked"] == [{"email": "a@example.com"}]  # 移除時一併登出


def test_remove_when_revoke_fails(admin, cf, setup):  # noqa: F811
    setup.router.post(REVOKE_URL).respond(403, json={"success": False, "errors": [{"code": 10000}]})
    r = admin.post("/admin/remove", data={"email": "a@example.com"}, headers=ORIGIN)
    assert "msg=removed-no-revoke" in r.headers["set-cookie"]
    assert cf["items"] == []  # 白名單照樣移除
    assert "沒辦法立刻登出" in admin.get("/admin").text


def test_add_duplicate_and_remove_missing(admin, cf):
    assert "msg=exists" in admin.post("/admin/add", data={"email": "A@example.com"}, headers=ORIGIN).headers["set-cookie"]
    assert "msg=missing" in admin.post("/admin/remove", data={"email": "z@example.com"}, headers=ORIGIN).headers["set-cookie"]
    assert cf["patches"] == [] and cf["revoked"] == []


@pytest.mark.parametrize("bad", ["", "not-an-email", "a@b", "<script>@x.com", "a" * 250 + "@example.com"])
def test_invalid_email(admin, cf, bad):
    assert "msg=invalid" in admin.post("/admin/add", data={"email": bad}, headers=ORIGIN).headers["set-cookie"]
    assert cf["patches"] == []


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example.com"}])
def test_cross_site_post_blocked(admin, cf, headers):
    assert admin.post("/admin/add", data={"email": "x@example.com"}, headers=headers).status_code == 403
    assert cf["patches"] == []


def test_cloudflare_failure_is_friendly(admin, setup):  # noqa: F811
    setup.router.get(f"{LIST_URL}/items").respond(500, json={"success": False, "errors": [{"code": 1}]})
    setup.router.get(f"{DRIVE_LIST_URL}/items").respond(500, json={"success": False, "errors": [{"code": 1}]})
    assert "讀取名單失敗" in admin.get("/admin").text
    assert "msg=error" in admin.post("/admin/add", data={"email": "x@example.com"}, headers=ORIGIN).headers["set-cookie"]


def test_message_is_escaped(admin, cf):
    admin.cookies.set("admin_flash", "msg=added&email=%3Cimg+src%3Dx+onerror%3Dalert%281%29%3E", path="/admin")
    r = admin.get("/admin")
    assert "<img src=x" not in r.text and "&lt;img" in r.text


def test_flash_shows_once(admin, cf):
    r = admin.post("/admin/add", data={"email": "new@example.com"}, headers=ORIGIN)
    assert r.headers["location"] == "/admin"  # 網址不帶訊息
    assert "已加入：new@example.com" in admin.get("/admin").text
    assert "已加入" not in admin.get("/admin").text  # 重新整理就不見


def test_normalize_email():
    assert normalize_email("Foo＠Example.COM ") == "foo@example.com"
    assert normalize_email("foo@example") is None


def test_drive_whitelist_add_remove(admin, cf):
    assert "網盤白名單" in admin.get("/admin").text
    r = admin.post("/admin/drive/add", data={"email": "Viewer@Example.com"}, headers=ORIGIN)
    assert "msg=drive-added" in r.headers["set-cookie"]
    assert [i["value"] for i in cf["drive"]] == ["viewer@example.com"]
    assert [i["value"] for i in cf["items"]] == ["a@example.com"]  # 表單白名單沒動
    assert "msg=drive-exists" in admin.post("/admin/drive/add", data={"email": "viewer@example.com"}, headers=ORIGIN).headers["set-cookie"]
    r = admin.post("/admin/drive/remove", data={"email": "viewer@example.com"}, headers=ORIGIN)
    assert "msg=drive-removed" in r.headers["set-cookie"]
    assert cf["drive"] == [] and cf["revoked"] == [{"email": "viewer@example.com"}]


def test_drive_whitelist_admin_only(cf):
    worker = TestClient(main.app, headers={"Cf-Access-Jwt-Assertion": access_token(email="worker@example.com")})
    assert worker.post("/admin/drive/add", data={"email": "x@example.com"}, headers=ORIGIN).status_code == 403
    assert cf["drive"] == []


def test_form_page_has_no_drive_link(admin, cf, monkeypatch):
    """表單頁對誰都不放網盤按鈕（管理者從 /admin 進網盤）。"""
    monkeypatch.setattr(main.settings, "drive_url", "https://drive.example.com")
    cf["drive"].append({"value": "viewer@example.com", "created_at": "2026-10-29T00:00:00Z"})
    viewer = TestClient(main.app, headers={"Cf-Access-Jwt-Assertion": access_token(email="viewer@example.com")})
    assert "drive.example.com" not in admin.get("/").text
    assert "drive.example.com" not in viewer.get("/").text
    assert 'href="https://drive.example.com"' in admin.get("/admin").text
