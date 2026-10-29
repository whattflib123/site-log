import json
import logging
import mimetypes
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.datastructures import UploadFile

from . import docgen, images, messages, pdf
from .naming import build_filename, clean_part
from .projects import ProjectError, ProjectStore
from .schemas import Submission
from .security import AccessVerifier, check_pin, verify_turnstile
from .settings import get_settings
from .storage import UploadError, WebDAVStorage
from .whitelist import Whitelist, WhitelistError, normalize_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("form-app")

settings = get_settings()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
limiter = Limiter(key_func=get_remote_address)
require_access = AccessVerifier(settings)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter
mimetypes.add_type("font/woff2", ".woff2")  # slim image 的 mimetypes 沒有 woff2
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

if not settings.turnstile_enabled:
    log.warning("Turnstile 驗證：關閉（TURNSTILE_SECRET 未設定，只適合本機）")
if not settings.access_enabled:
    log.warning("Cloudflare Access 驗證：關閉（ACCESS_TEAM_DOMAIN / ACCESS_AUD 未設定，只適合本機）")

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_TYPE = "application/pdf"
def error(status: int, texts: dict[str, str]) -> JSONResponse:
    """texts 是 messages.text() 回傳的 {語言: 訊息}；表單頁依使用者選的語言顯示。"""
    return JSONResponse(messages.body(texts), status_code=status)


@app.exception_handler(RateLimitExceeded)
def rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    log.warning("rate limited ip=%s", get_remote_address(request))
    return error(429, messages.text("rate_limited"))


@app.middleware("http")
async def limit_body(request: Request, call_next):
    # Caddy 也有上限；這裡再擋一次，避免繞過 Caddy 時被塞爆記憶體
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > settings.max_body_mb * 1024 * 1024):
        return error(413, messages.text("too_large", mb=settings.max_body_mb))
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=604800"
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


PAGE_CSP = "; ".join([
    "default-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
])


@app.get("/", response_class=HTMLResponse)
def index(request: Request, email: str = Depends(require_access)) -> HTMLResponse:
    nonce = secrets.token_urlsafe(16)
    response = templates.TemplateResponse(request, "index.html", {
        "csp_nonce": nonce,
        "turnstile_site_key": settings.turnstile_site_key,
        "pin_enabled": bool(settings.upload_pin),
        "max_photos": settings.max_photos,
    })
    response.headers["Content-Security-Policy"] = "; ".join([
        "default-src 'self'",
        f"script-src 'nonce-{nonce}' https://challenges.cloudflare.com",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self'",
        "img-src 'self' blob: data:",
        "frame-src https://challenges.cloudflare.com",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
    ])
    return response


def describe(exc: ValidationError) -> dict[str, str]:
    """欄位驗證錯誤 → {語言: 訊息}。"""
    err = exc.errors()[0]
    loc = [str(x) for x in err["loc"]]
    where = {lang: "" for lang in messages.LANGS}
    if len(loc) >= 2 and loc[0] == "entries" and loc[1].isdigit():
        where = messages.text("where", n=int(loc[1]) + 1)
        loc = loc[2:]
    field = loc[0] if loc else ""
    label = messages.label(field)
    kind = err["type"]
    if kind == "string_too_long":
        return messages.text("too_long", where=where, label=label, n=err["ctx"]["max_length"])
    if kind in ("too_short", "missing") and field == "entries":
        return messages.text("need_entry")
    if kind in ("string_too_short", "missing"):
        return messages.text("required", where=where, label=label)
    if kind == "too_long":
        return messages.text("too_many", label=label, n=err["ctx"]["max_length"])
    return messages.text("invalid", where=where, label=label)


@app.post("/submit")
@limiter.limit(settings.rate_limit)
async def submit(request: Request, email: str = Depends(require_access)) -> Response:
    form = await request.form(max_files=settings.max_photos, max_fields=20, max_part_size=1024 * 1024)

    if not check_pin(settings, str(form.get("pin", ""))):
        return error(403, messages.text("wrong_pin"))
    client_ip = get_remote_address(request)
    token = str(form.get("cf-turnstile-response", ""))
    if not await run_in_threadpool(verify_turnstile, settings, token, client_ip):
        return error(403, messages.text("turnstile_failed"))

    try:
        sub = Submission.model_validate({
            "category": form.get("category"),
            "project_name": form.get("project_name"),
            "project_title": form.get("project_title", ""),
            "code": form.get("code", ""),
            "filename": form.get("filename"),
            "entries": json.loads(str(form.get("entries") or "[]")),
        })
    except json.JSONDecodeError:
        return error(422, messages.text("bad_data"))
    except ValidationError as exc:
        return error(422, describe(exc))

    # 工程只能從管理者的清單選，檔名和網盤分類才會一致
    try:
        names = {p["name"] for p in ProjectStore(settings.projects_file).items()}
    except ProjectError:
        return error(503, messages.text("projects_unavailable"))
    if sub.project_name not in names:
        return error(422, messages.text("unknown_project"))

    uploads = [f for f in form.getlist("photos") if isinstance(f, UploadFile)]
    if len(uploads) != len(sub.entries):
        return error(422, messages.text("photo_missing"))
    photos = []
    for i, upload in enumerate(uploads, start=1):
        raw = await upload.read(settings.max_photo_mb * 1024 * 1024 + 1)
        if len(raw) > settings.max_photo_mb * 1024 * 1024:
            return error(413, messages.text("photo_too_large", i=i, mb=settings.max_photo_mb))
        try:
            photos.append(await run_in_threadpool(images.normalize, raw))
        except images.InvalidImage as exc:
            log.warning("invalid photo #%d: %s", i, exc)
            return error(422, messages.text("photo_unreadable", i=i))

    data = await run_in_threadpool(docgen.render, sub, photos)
    pdf_data = await run_in_threadpool(pdf.convert, settings, data) if settings.gotenberg_url else None
    now = datetime.now()
    folder = [f"{now:%Y}", f"{now:%m}"]
    filename = build_filename(now, sub.project_name, sub.category_name, sub.filename)

    storage = WebDAVStorage(settings)
    try:
        saved = await run_in_threadpool(storage.save, folder, filename, data)
        saved_name = saved.rsplit("/", 1)[-1]
        pdf_name = saved_name.removesuffix(".docx") + ".pdf"
        pdf_status = "failed" if settings.gotenberg_url else ""
        if pdf_data:
            try:
                pdf_name = (await run_in_threadpool(storage.save, folder, pdf_name, pdf_data, PDF_TYPE)).rsplit("/", 1)[-1]
                pdf_status = "saved"
            except UploadError:
                # Word 已經存進網盤，這時回錯誤會讓使用者重送、多存一份 Word；照樣把 PDF 給手機
                pdf_status = "not-saved"
    except UploadError:
        return error(502, messages.text("save_failed"))
    finally:
        storage.client.close()

    log.info("saved user=%s ip=%s path=%s bytes=%d photos=%d pdf=%s", email or "-", client_ip, saved, len(data),
             len(photos), pdf_status or "off")
    body, media, download = (pdf_data, PDF_TYPE, pdf_name) if pdf_data else (data, DOCX_TYPE, saved_name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(download)}",
        "X-Saved-As": quote(saved_name),
        "X-Download-As": quote(download),
    }
    if pdf_status:
        headers["X-Pdf"] = pdf_status
    return Response(body, media_type=media, headers=headers)


@app.get("/projects")
def shared_projects(email: str = Depends(require_access)) -> JSONResponse:
    try:
        items = ProjectStore(settings.projects_file).items()
    except ProjectError:
        return error(503, messages.text("projects_unavailable"))
    return JSONResponse([{"id": p["id"], "name": p["name"], "title": p.get("title", "")} for p in items])


# ---------- 白名單管理頁（給 ADMIN_EMAILS 裡的人）----------

ADMIN_MESSAGES = {
    "added": "已加入",
    "removed": "已移除並登出",
    "removed-no-revoke": "已移除，但沒辦法立刻登出，請系統管理員到 Cloudflare 撤銷對方的登入",
    "drive-added": "已加入網盤白名單",
    "drive-removed": "已從網盤白名單移除並登出",
    "drive-removed-no-revoke": "已從網盤白名單移除，但沒辦法立刻登出，請系統管理員到 Cloudflare 撤銷對方的登入",
    "drive-exists": "已經在網盤白名單裡",
    "drive-missing": "網盤白名單裡沒有這個 email",
    "invalid": "email 格式不正確",
    "exists": "已經在白名單裡",
    "missing": "白名單裡沒有這個 email",
    "error": "連不到 Cloudflare，請稍後再試",
    "project-added": "已新增工程",
    "project-removed": "已刪除工程",
    "project-invalid": "工程簡稱必填，最多 40 字，不能有 \\ / : * ? \" < > | # %",
    "project-exists": "已經有同名的工程",
    "project-missing": "找不到這個工程，可能已經刪除",
    "project-error": "工程清單存檔失敗，請稍後再試",
}
ADMIN_OK = {"added", "removed", "drive-added", "drive-removed", "project-added", "project-removed"}


def require_admin(request: Request, email: str = Depends(require_access)) -> str:
    if not settings.admin_enabled or email.lower() not in settings.admins:
        raise HTTPException(403, "沒有管理權限")
    return email.lower()


def same_origin(request: Request) -> bool:
    # 擋跨站送出表單（CSRF）：瀏覽器送 POST 一定帶 Origin
    origin = request.headers.get("origin", "")
    return origin.split("://", 1)[-1] == request.headers.get("host", "")


FLASH_COOKIE = "admin_flash"


def back(code: str, email: str = "") -> RedirectResponse:
    """操作完回管理頁。結果放在一次性 cookie（不放網址），顯示一次就清掉，重新整理就不見。"""
    response = RedirectResponse("/admin", status_code=303)
    value = urlencode({"msg": code, "email": email} if email else {"msg": code})
    response.set_cookie(FLASH_COOKIE, value, max_age=60, path="/admin", httponly=True, samesite="strict")
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, admin: str = Depends(require_admin)) -> HTMLResponse:
    flash = parse_qs(request.cookies.get(FLASH_COOKIE, ""))
    msg, email = flash.get("msg", [""])[0], flash.get("email", [""])[0]
    whitelist = Whitelist(settings)
    try:
        items, failed = whitelist.items(), False
    except WhitelistError:
        items, failed = [], True
    finally:
        whitelist.client.close()
    drive_items, drive_failed = [], False
    if settings.drive_admin_enabled:
        drive_list = Whitelist(settings, list_id=settings.cf_drive_list_id)
        try:
            drive_items = drive_list.items()
        except WhitelistError:
            drive_failed = True
        finally:
            drive_list.client.close()
    try:
        projects, projects_failed = ProjectStore(settings.projects_file).items(), False
    except ProjectError:
        projects, projects_failed = [], True
    response = templates.TemplateResponse(request, "admin.html", {
        "items": items,
        "failed": failed,
        "drive_enabled": settings.drive_admin_enabled,
        "drive_items": drive_items,
        "drive_failed": drive_failed,
        "drive_share_url": settings.drive_share_url,
        "projects": projects,
        "projects_failed": projects_failed,
        "admin": admin,
        "message": ADMIN_MESSAGES.get(msg, ""),
        "ok": msg in ADMIN_OK,
        "subject": email,
        "drive_url": settings.drive_url,
    })
    response.headers["Content-Security-Policy"] = PAGE_CSP
    if FLASH_COOKIE in request.cookies:
        response.delete_cookie(FLASH_COOKIE, path="/admin")
    return response


async def admin_action(request: Request, admin: str, action: str, drive: bool = False) -> RedirectResponse:
    """drive=False 改表單白名單，drive=True 改網盤白名單。"""
    if not same_origin(request):
        raise HTTPException(403, "請從管理頁操作")
    if drive and not settings.drive_admin_enabled:
        raise HTTPException(404)
    form = await request.form(max_fields=5, max_files=0)
    email = normalize_email(str(form.get("email", "")))
    if not email:
        return back("invalid")
    prefix, name = ("drive-", "drive-list") if drive else ("", "whitelist")
    whitelist = Whitelist(settings, list_id=settings.cf_drive_list_id if drive else "")
    try:
        current = {i["value"].lower() for i in whitelist.items()}
        if action == "add":
            if email in current:
                return back(prefix + "exists", email)
            whitelist.add(email, admin)
            log.info("%s add %s by %s", name, email, admin)
            return back(prefix + "added", email)
        if email not in current:
            return back(prefix + "missing", email)
        whitelist.remove(email)
        log.info("%s remove %s by %s", name, email, admin)
        # 對方已經拿到的登入要等到期（30 天）才會失效，所以移除時一併撤銷。
        # Cloudflare 的撤銷是整個帳戶的登入，表單和網盤都會被登出，還在另一份清單的人重新收驗證碼即可
        try:
            whitelist.revoke(email)
        except WhitelistError:
            return back(prefix + "removed-no-revoke", email)
        log.info("revoked %s by %s", email, admin)
        return back(prefix + "removed", email)
    except WhitelistError:
        return back("error", email)
    finally:
        whitelist.client.close()


@app.post("/admin/add")
@limiter.limit("30/minute")
async def admin_add(request: Request, admin: str = Depends(require_admin)) -> RedirectResponse:
    return await admin_action(request, admin, "add")


@app.post("/admin/remove")
@limiter.limit("30/minute")
async def admin_remove(request: Request, admin: str = Depends(require_admin)) -> RedirectResponse:
    return await admin_action(request, admin, "remove")


@app.post("/admin/drive/add")
@limiter.limit("30/minute")
async def admin_drive_add(request: Request, admin: str = Depends(require_admin)) -> RedirectResponse:
    return await admin_action(request, admin, "add", drive=True)


@app.post("/admin/drive/remove")
@limiter.limit("30/minute")
async def admin_drive_remove(request: Request, admin: str = Depends(require_admin)) -> RedirectResponse:
    return await admin_action(request, admin, "remove", drive=True)


@app.post("/admin/projects/add")
@limiter.limit("30/minute")
async def admin_project_add(request: Request, admin: str = Depends(require_admin)) -> RedirectResponse:
    if not same_origin(request):
        raise HTTPException(403, "請從管理頁操作")
    form = await request.form(max_fields=5, max_files=0)
    # 工程簡稱會出現在檔名裡，先用檔名規則清一次，避免存進網盤時名稱和清單上不同
    name = " ".join(str(form.get("name", "")).split())
    title = " ".join(str(form.get("title", "")).split())[:100]
    if not name or len(name) > 40 or clean_part(name) != name:
        return back("project-invalid", name[:40])
    try:
        project = ProjectStore(settings.projects_file).add(name, title, admin)
    except ProjectError:
        return back("project-error", name)
    if project is None:
        return back("project-exists", name)
    log.info("project add %s by %s", name, admin)
    return back("project-added", name)


@app.post("/admin/projects/remove")
@limiter.limit("30/minute")
async def admin_project_remove(request: Request, admin: str = Depends(require_admin)) -> RedirectResponse:
    if not same_origin(request):
        raise HTTPException(403, "請從管理頁操作")
    form = await request.form(max_fields=5, max_files=0)
    try:
        project = ProjectStore(settings.projects_file).remove(str(form.get("id", "")))
    except ProjectError:
        return back("project-error")
    if project is None:
        return back("project-missing")
    log.info("project remove %s by %s", project["name"], admin)
    return back("project-removed", project["name"])
