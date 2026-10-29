from datetime import datetime

import pytest

from app.naming import build_filename, clean_part, numbered

NOW = datetime(2026, 10, 28, 9, 5, 7)


@pytest.mark.parametrize("raw, expected", [
    ("工審-026", "工審-026"),
    ("../../etc/passwd", "_.._etc_passwd"),
    ("..\\..\\windows", "_.._windows"),
    ('a:b*c?d"e<f>g|h', "a_b_c_d_e_f_g_h"),
    ("50% #3", "50_ _3"),
    ("  多個   空白\t\n換行  ", "多個 空白 換行"),
    ("...隱藏檔", "隱藏檔"),
    ("結尾點...", "結尾點"),
    ("零寬​字元‮反轉", "零寬字元反轉"),
    ("控制\x00字元\x1f", "控制_字元"),  # \x1f 算空白，結尾空白會去掉
    ("", ""),
    ("   ", ""),
])
def test_clean_part(raw, expected):
    assert clean_part(raw) == expected


def test_clean_part_limits_length():
    assert len(clean_part("長" * 200)) == 60


def test_build_filename_joins_parts():
    assert build_filename(NOW, "工程一", "施工照片", "工審-026") == "20261028-090507_工程一_施工照片_工審-026.docx"


def test_build_filename_skips_empty_parts():
    assert build_filename(NOW, "工程一", "", "  ") == "20261028-090507_工程一.docx"


def test_build_filename_all_empty():
    assert build_filename(NOW, "", " . ") == "20261028-090507_未命名.docx"


def test_build_filename_never_contains_path_separators():
    name = build_filename(NOW, "../a/b", "c\\d", "e/../../f")
    assert "/" not in name and "\\" not in name
    assert name.endswith(".docx")


def test_numbered():
    assert numbered("a_b.docx", 2) == "a_b-2.docx"
    assert numbered("noext", 3) == "noext-3"
