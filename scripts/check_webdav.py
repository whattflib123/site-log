"""從 form-app 容器內測 Cloudreve WebDAV（/dav 不對外開放）。

用法：docker compose exec -T form-app python - < scripts/check_webdav.py
"""
import base64, os, urllib.request, urllib.error
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None
opener = urllib.request.build_opener(NoRedirect)
auth = base64.b64encode(f"{os.environ['WEBDAV_USER']}:{os.environ['WEBDAV_PASSWORD']}".encode()).decode()
def dav(method, path, data=None, **headers):
    req = urllib.request.Request(os.environ["WEBDAV_URL"] + path, data=data, method=method,
                                 headers={"Authorization": "Basic " + auth, **headers})
    try:
        with opener.open(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        # 儲存策略是 R2 時 GET 會 302 到預簽章網址；不能帶 Basic auth 過去，R2 會回 400
        if e.code in (301, 302, 307) and e.headers.get("Location"):
            with urllib.request.urlopen(e.headers["Location"]) as r:
                return r.status, r.read()
        return e.code, b""
print("MKCOL", dav("MKCOL", "/test")[0])                       # 201
print("PUT  ", dav("PUT", "/test/hello.txt", b"hello")[0])     # 201
print("GET  ", dav("GET", "/test/hello.txt"))                  # (200, b'hello')
print("DELETE", dav("DELETE", "/test")[0])                     # 204
