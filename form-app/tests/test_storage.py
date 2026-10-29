import httpx
import pytest
import respx

from app.settings import Settings
from app.storage import UploadError, WebDAVStorage

BASE = "http://dav.test/dav"
DIR = BASE + "/2026/10"
NAME = "20261028-090507_工程一_施工照片_工審-026.docx"
ENC = "20261028-090507_%E5%B7%A5%E7%A8%8B%E4%B8%80_%E6%96%BD%E5%B7%A5%E7%85%A7%E7%89%87_%E5%B7%A5%E5%AF%A9-026.docx"


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def storage(sleeps):
    settings = Settings(webdav_url=BASE, webdav_user="u", webdav_password="p", upload_root="/")
    return WebDAVStorage(settings, sleep=sleeps.append)


def mock_dirs(mkcol_status=201):
    respx.request("MKCOL", BASE + "/2026").respond(mkcol_status)
    respx.request("MKCOL", DIR).respond(mkcol_status)


@respx.mock
def test_save_creates_dirs_and_puts(storage):
    mock_dirs()
    respx.head(f"{DIR}/{ENC}").respond(404)
    put = respx.put(f"{DIR}/{ENC}").respond(201)
    assert storage.save(["2026", "10"], NAME, b"docx") == f"/2026/10/{NAME}"
    assert put.calls.last.request.content == b"docx"
    assert put.calls.last.request.headers["authorization"].startswith("Basic ")


@respx.mock
def test_existing_dirs_are_fine(storage):
    mock_dirs(405)
    respx.head(f"{DIR}/{ENC}").respond(404)
    respx.put(f"{DIR}/{ENC}").respond(201)
    storage.save(["2026", "10"], NAME, b"docx")


@respx.mock
def test_same_name_gets_number(storage):
    mock_dirs()
    respx.head(f"{DIR}/a.docx").respond(200)
    respx.head(f"{DIR}/a-2.docx").respond(200)
    respx.head(f"{DIR}/a-3.docx").respond(404)
    put = respx.put(f"{DIR}/a-3.docx").respond(201)
    assert storage.save(["2026", "10"], "a.docx", b"x") == "/2026/10/a-3.docx"
    assert put.called


@respx.mock
def test_upload_root_prefix(sleeps):
    settings = Settings(webdav_url=BASE + "/", upload_root="/sub/dir/")
    s = WebDAVStorage(settings, sleep=sleeps.append)
    for p in ("/sub", "/sub/dir", "/sub/dir/2026"):
        respx.request("MKCOL", BASE + p).respond(201)
    respx.head(BASE + "/sub/dir/2026/a.docx").respond(404)
    respx.put(BASE + "/sub/dir/2026/a.docx").respond(201)
    assert s.save(["2026"], "a.docx", b"x") == "/sub/dir/2026/a.docx"


@respx.mock
def test_retries_server_errors_with_backoff(storage, sleeps):
    mock_dirs()
    respx.head(f"{DIR}/a.docx").respond(404)
    respx.put(f"{DIR}/a.docx").mock(side_effect=[httpx.Response(503), httpx.ConnectError("down"), httpx.Response(201)])
    storage.save(["2026", "10"], "a.docx", b"x")
    assert sleeps == [1, 2]


@respx.mock
def test_gives_up_after_three_retries(storage, sleeps):
    mock_dirs()
    respx.head(f"{DIR}/a.docx").respond(404)
    put = respx.put(f"{DIR}/a.docx").respond(500)
    with pytest.raises(UploadError):
        storage.save(["2026", "10"], "a.docx", b"x")
    assert put.call_count == 4
    assert sleeps == [1, 2, 4]


@respx.mock
def test_auth_error_is_not_retried(storage, sleeps):
    mkcol = respx.request("MKCOL", BASE + "/2026").respond(401)
    with pytest.raises(UploadError):
        storage.save(["2026", "10"], "a.docx", b"x")
    assert mkcol.call_count == 1
    assert sleeps == []


@respx.mock
def test_path_segments_are_encoded(storage):
    # 檔名裡就算有 / 也只會是一層（naming 已經清掉，這裡再保險一次）
    respx.request("MKCOL", BASE + "/a%2Fb").respond(201)
    respx.head(BASE + "/a%2Fb/x%3Fy.docx").respond(404)
    put = respx.put(BASE + "/a%2Fb/x%3Fy.docx").respond(201)
    storage.save(["a/b"], "x?y.docx", b"x")
    assert put.called
