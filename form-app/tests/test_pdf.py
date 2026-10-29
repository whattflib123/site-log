from urllib.parse import unquote

import httpx
import pytest

from app import main
from app.storage import UploadError

from test_api import client, post, setup  # noqa: F401  (fixture)

GOTENBERG = "http://gotenberg.test"
CONVERT_URL = f"{GOTENBERG}/forms/libreoffice/convert"
FAKE_PDF = b"%PDF-1.7\n fake"


@pytest.fixture
def pdf_on(monkeypatch, setup):  # noqa: F811
    monkeypatch.setattr(main.settings, "gotenberg_url", GOTENBERG)
    return setup.router.post(CONVERT_URL)


def test_pdf_downloaded_and_both_saved(client, jpeg, setup, pdf_on):  # noqa: F811
    pdf_on.respond(200, content=FAKE_PDF)
    res = post(client, jpeg)
    assert res.status_code == 200, res.text
    assert res.content == FAKE_PDF and res.headers["content-type"] == "application/pdf"
    assert res.headers["x-pdf"] == "saved"
    docx_name, pdf_name = unquote(res.headers["x-saved-as"]), unquote(res.headers["x-download-as"])
    assert pdf_name == docx_name.removesuffix(".docx") + ".pdf"
    (_, n1, d1), (_, n2, d2) = setup.saved
    assert (n1, n2) == (docx_name, pdf_name)
    assert d1[:4] == b"PK\x03\x04" and d2 == FAKE_PDF
    # 送給 Gotenberg 的是剛產生的 Word
    assert b"PK\x03\x04" in pdf_on.calls.last.request.content


@pytest.mark.parametrize("reply", [
    httpx.Response(500, text="boom"),
    httpx.Response(200, content=b"not a pdf"),
    httpx.ConnectError("down"),
])
def test_conversion_failure_falls_back_to_word(client, jpeg, setup, pdf_on, reply):  # noqa: F811
    pdf_on.mock(side_effect=reply) if isinstance(reply, Exception) else pdf_on.mock(return_value=reply)
    res = post(client, jpeg)
    assert res.status_code == 200
    assert res.content[:4] == b"PK\x03\x04" and res.headers["x-pdf"] == "failed"
    assert len(setup.saved) == 1  # 只存 Word


def test_pdf_save_failure_still_downloads_pdf(client, jpeg, setup, pdf_on, monkeypatch):  # noqa: F811
    pdf_on.respond(200, content=FAKE_PDF)

    def save(self, folder, name, data, *rest):
        if name.endswith(".pdf"):
            raise UploadError("pdf")
        setup.saved.append((folder, name, data))
        return "/" + "/".join(folder + [name])

    monkeypatch.setattr(main.WebDAVStorage, "save", save)
    res = post(client, jpeg)
    assert res.status_code == 200 and res.content == FAKE_PDF
    assert res.headers["x-pdf"] == "not-saved"
    assert len(setup.saved) == 1


def test_pdf_off_by_default(client, jpeg):  # noqa: F811
    res = post(client, jpeg)
    assert res.content[:4] == b"PK\x03\x04" and "x-pdf" not in res.headers
