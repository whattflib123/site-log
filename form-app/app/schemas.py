from datetime import date as Date
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# 與前端 index.html 的 CATEGORIES 一致；doc_title 是 Word 最上面的大標題
CATEGORIES: dict[str, dict[str, str]] = {
    "self-check": {"name": "自主檢查表"},
    "material": {"name": "材料進場"},
    "daily": {"name": "施工日誌"},
    "spot-check": {"name": "抽查紀錄表"},
    "attendance": {"name": "出勤紀錄"},
    "defect": {"name": "缺失改善"},
    "photo": {"name": "施工照片", "doc_title": "工程施工照片保存卡"},
}


def Text(max_length: int, min_length: int = 0):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: Optional[Date] = None
    item: Text(100) = ""
    location: Text(100) = ""
    desc: Text(2000) = ""


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Annotated[str, Field(pattern="^(" + "|".join(CATEGORIES) + ")$")]
    project_name: Text(40, min_length=1)  # 工程列表上的名稱（例：工程一）
    project_title: Text(100) = ""  # Word 上的「工程名稱」
    code: Text(60) = ""
    filename: Text(80, min_length=1)
    entries: Annotated[list[Entry], Field(min_length=1, max_length=30)]

    @property
    def category_name(self) -> str:
        return CATEGORIES[self.category]["name"]

    @property
    def doc_title(self) -> str:
        cat = CATEGORIES[self.category]
        return cat.get("doc_title", cat["name"])
