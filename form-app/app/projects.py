"""共用工程清單：管理者在 /admin 維護，所有人的表單首頁都看得到。存成一個 JSON 檔。"""
import json
import logging
import os
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("form-app.projects")

MAX_PROJECTS = 200
_lock = threading.Lock()


class ProjectError(Exception):
    pass


class ProjectStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def items(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            log.error("read %s failed: %s", self.path, type(exc).__name__)
            raise ProjectError from exc
        return [p for p in data if isinstance(p, dict) and {"id", "name"} <= p.keys()]

    def _write(self, items: list[dict]) -> None:
        # 先寫同目錄的暫存檔再換名，寫到一半當機也不會留下壞掉的清單
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("write %s failed: %s", self.path, type(exc).__name__)
            raise ProjectError from exc

    def add(self, name: str, title: str, by: str) -> Optional[dict]:
        """名稱重複回傳 None。"""
        with _lock:
            items = self.items()
            if any(p["name"] == name for p in items):
                return None
            if len(items) >= MAX_PROJECTS:
                raise ProjectError("too many projects")
            project = {"id": "s" + secrets.token_hex(6), "name": name, "title": title,
                       "note": f"{by} 於 {datetime.now():%Y-%m-%d %H:%M} 新增"}
            self._write(items + [project])
            return project

    def remove(self, project_id: str) -> Optional[dict]:
        """找不到回傳 None。"""
        with _lock:
            items = self.items()
            found = next((p for p in items if p["id"] == project_id), None)
            if found:
                self._write([p for p in items if p["id"] != project_id])
            return found
