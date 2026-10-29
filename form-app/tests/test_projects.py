from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main

from test_admin import ORIGIN, admin, cf  # noqa: F401  (fixture)
from test_api import access_token, setup  # noqa: F401  (autouse fixture)

STORE = Path(main.settings.projects_file)


@pytest.fixture(autouse=True)
def empty_store(cf):  # noqa: F811  (管理頁也會讀白名單)
    STORE.unlink(missing_ok=True)
    yield
    STORE.unlink(missing_ok=True)


@pytest.fixture
def worker():
    return TestClient(main.app, headers={"Cf-Access-Jwt-Assertion": access_token(email="worker@example.com")})


def add(admin, name, title=""):  # noqa: F811
    return admin.post("/admin/projects/add", data={"name": name, "title": title}, headers=ORIGIN)


def test_add_list_remove(admin, worker):  # noqa: F811
    assert worker.get("/projects").json() == []
    r = add(admin, "  河濱公園  ", "河濱公園環境改善工程")
    assert r.status_code == 303 and "msg=project-added" in r.headers["set-cookie"]

    [p] = worker.get("/projects").json()
    assert p["name"] == "河濱公園" and p["title"] == "河濱公園環境改善工程"
    assert set(p) == {"id", "name", "title"}  # 誰加的只給管理頁看

    page = admin.get("/admin").text
    assert "河濱公園" in page and "boss@example.com 於" in page

    r = admin.post("/admin/projects/remove", data={"id": p["id"]}, headers=ORIGIN)
    assert "msg=project-removed" in r.headers["set-cookie"]
    assert worker.get("/projects").json() == []


def test_duplicate_and_missing(admin):  # noqa: F811
    add(admin, "工程A")
    assert "msg=project-exists" in add(admin, "工程A").headers["set-cookie"]
    r = admin.post("/admin/projects/remove", data={"id": "nope"}, headers=ORIGIN)
    assert "msg=project-missing" in r.headers["set-cookie"]


@pytest.mark.parametrize("bad", ["", "   ", "a" * 41, "工程/一", "工程#1", "工程​一"])
def test_invalid_names(admin, bad):  # noqa: F811
    assert "msg=project-invalid" in add(admin, bad).headers["set-cookie"]
    assert not STORE.exists()


def test_only_admin_can_change(worker):
    assert worker.post("/admin/projects/add", data={"name": "x"}, headers=ORIGIN).status_code == 403
    assert worker.post("/admin/projects/remove", data={"id": "x"}, headers=ORIGIN).status_code == 403
    assert not STORE.exists()


def test_cross_site_blocked(admin):  # noqa: F811
    r = admin.post("/admin/projects/add", data={"name": "x"}, headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403 and not STORE.exists()


def test_projects_needs_login():
    assert TestClient(main.app).get("/projects").status_code == 403


def test_broken_file_is_friendly(admin, worker):  # noqa: F811
    STORE.write_text("{not json", encoding="utf-8")
    assert worker.get("/projects").status_code == 503
    assert "讀取工程清單失敗" in admin.get("/admin").text
    assert "msg=project-error" in add(admin, "工程B").headers["set-cookie"]
    assert STORE.read_text(encoding="utf-8") == "{not json"  # 讀不到就不覆蓋


def test_title_is_escaped(admin):  # noqa: F811
    # 簡稱不能有 < >（檔名規則），Word 上的工程名稱可以有，所以要確認頁面有跳脫
    add(admin, "工程C", "<b>工程</b>")
    page = admin.get("/admin").text
    assert "<b>工程</b>" not in page and "&lt;b&gt;工程&lt;/b&gt;" in page
