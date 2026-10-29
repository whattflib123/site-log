from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Cloudreve WebDAV（compose 內網）
    webdav_url: str = "http://cloudreve:5212/dav"
    webdav_user: str = ""
    webdav_password: str = ""
    # 相對於 WebDAV 帳號根目錄；帳號根目錄已限定為網盤的 /form-output
    upload_root: str = "/"
    webdav_timeout: float = 30.0

    # 防濫用
    rate_limit: str = "5/minute"
    max_body_mb: int = 60
    max_photos: int = 30
    max_photo_mb: int = 8
    # 選填的第二層「上傳代碼」；留空不檢查
    upload_pin: str = ""

    # 頁首「網盤」連結；留空不顯示（例：https://drive.example.com）
    drive_url: str = ""

    # Cloudflare Turnstile；secret 留空 = 不驗證（只適合本機）
    turnstile_site_key: str = ""
    turnstile_secret: str = ""
    # 填了就檢查 siteverify 回傳的 hostname（上線時填 FORM_DOMAIN 的網域）
    turnstile_hostname: str = ""

    # Cloudflare Access；兩個都填才驗證 Cf-Access-Jwt-Assertion
    access_team_domain: str = ""
    access_aud: str = ""

    # /admin 白名單管理頁：可以進管理頁的 email（逗號分隔），和 Cloudflare Zero Trust email 清單
    admin_emails: str = ""
    cf_account_id: str = ""
    cf_list_id: str = ""
    # 只給「Zero Trust 編輯」權限的 API 權杖（也用來撤銷被移除者的登入）
    cf_api_token: str = ""

    # 網盤白名單（Cloudflare Access 應用程式「drive」引用的 email 清單）；空白 = /admin 不顯示這一區
    cf_drive_list_id: str = ""
    # 網盤白名單的人沒有網盤帳號，表單頁的「網盤」連結給他們 form-output 的分享連結
    drive_share_url: str = ""

    # 管理者維護的共用工程清單（compose 掛 ./data/form-app 到 /data）
    projects_file: str = "/data/projects.json"

    # Word 轉 PDF 的 Gotenberg（compose 內網）；留空 = 不轉，手機照舊下載 Word
    gotenberg_url: str = ""
    pdf_timeout: float = 70.0  # 比 Gotenberg 的 --api-timeout=60s 長一點

    @property
    def admins(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def admin_enabled(self) -> bool:
        return bool(self.access_enabled and self.admins and self.cf_account_id and self.cf_list_id and self.cf_api_token)

    @property
    def drive_admin_enabled(self) -> bool:
        return bool(self.admin_enabled and self.cf_drive_list_id)

    @property
    def turnstile_enabled(self) -> bool:
        return bool(self.turnstile_secret)

    @property
    def access_enabled(self) -> bool:
        return bool(self.access_team_domain and self.access_aud)


@lru_cache
def get_settings() -> Settings:
    return Settings()
