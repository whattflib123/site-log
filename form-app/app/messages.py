"""回給表單頁的錯誤訊息：中文、English、Tiếng Việt、ไทย。

表單頁依使用者選的語言顯示 detail_<語言>，沒有就退回英文、再退回中文（detail）。
越南文、泰文是非母語翻譯，請母語人士校對後直接改這裡。
"""
LANGS = ("zh", "en", "vi", "th")

MESSAGES: dict[str, dict[str, str]] = {
    "rate_limited": {
        "zh": "送出太頻繁，請等一分鐘後再試",
        "en": "Too many submissions. Please wait a minute and try again.",
        "vi": "Gửi quá nhiều lần. Vui lòng đợi một phút rồi thử lại.",
        "th": "ส่งบ่อยเกินไป กรุณารอหนึ่งนาทีแล้วลองใหม่",
    },
    "too_large": {
        "zh": "檔案太大，整份最多 {mb}MB，請減少照片張數",
        "en": "Too large: {mb}MB max per submission. Please use fewer photos.",
        "vi": "Dung lượng quá lớn: tối đa {mb}MB mỗi lần gửi. Vui lòng bớt số ảnh.",
        "th": "ไฟล์ใหญ่เกินไป ส่งได้ไม่เกิน {mb}MB ต่อครั้ง กรุณาลดจำนวนรูป",
    },
    "wrong_pin": {
        "zh": "上傳代碼不正確",
        "en": "Wrong upload code",
        "vi": "Mã tải lên không đúng",
        "th": "รหัสอัปโหลดไม่ถูกต้อง",
    },
    "turnstile_failed": {
        "zh": "人機驗證失敗或已過期，請重新勾選驗證後再送出",
        "en": "Human verification failed or expired. Please verify again and resubmit.",
        "vi": "Xác minh thất bại hoặc đã hết hạn. Vui lòng xác minh lại rồi gửi.",
        "th": "การยืนยันไม่สำเร็จหรือหมดอายุ กรุณายืนยันอีกครั้งแล้วส่งใหม่",
    },
    "bad_data": {
        "zh": "資料格式不正確，請重新整理頁面後再試",
        "en": "Invalid data. Please reload the page and try again.",
        "vi": "Dữ liệu không hợp lệ. Vui lòng tải lại trang rồi thử lại.",
        "th": "ข้อมูลไม่ถูกต้อง กรุณาโหลดหน้าใหม่แล้วลองอีกครั้ง",
    },
    "projects_unavailable": {
        "zh": "讀取工程清單失敗，請稍後再試",
        "en": "Could not load the project list. Please try again later.",
        "vi": "Không tải được danh sách công trình. Vui lòng thử lại sau.",
        "th": "โหลดรายการโครงการไม่สำเร็จ กรุณาลองใหม่ภายหลัง",
    },
    "unknown_project": {
        "zh": "這個工程不在工程清單裡（可能已被管理者刪除），請回首頁重新選擇",
        "en": "This project is no longer on the list (it may have been removed). Please go back and choose again.",
        "vi": "Công trình này không còn trong danh sách (có thể đã bị quản lý xóa). Vui lòng quay lại và chọn lại.",
        "th": "โครงการนี้ไม่อยู่ในรายการแล้ว (ผู้ดูแลอาจลบไปแล้ว) กรุณากลับไปเลือกใหม่",
    },
    "photo_missing": {
        "zh": "每一筆都要有照片",
        "en": "Every record needs a photo",
        "vi": "Mỗi mục đều phải có ảnh",
        "th": "ทุกรายการต้องมีรูป",
    },
    "photo_too_large": {
        "zh": "第 {i} 筆的照片太大（最多 {mb}MB）",
        "en": "Record {i}: photo is too large (max {mb}MB)",
        "vi": "Mục {i}: ảnh quá lớn (tối đa {mb}MB)",
        "th": "รายการที่ {i}: รูปใหญ่เกินไป (ไม่เกิน {mb}MB)",
    },
    "photo_unreadable": {
        "zh": "第 {i} 筆的照片無法讀取，請換一張",
        "en": "Record {i}: photo could not be read. Please use another one.",
        "vi": "Mục {i}: không đọc được ảnh. Vui lòng dùng ảnh khác.",
        "th": "รายการที่ {i}: อ่านรูปไม่ได้ กรุณาใช้รูปอื่น",
    },
    "save_failed": {
        "zh": "Word 已產生，但存進網盤失敗。畫面上的資料都還在，請稍後再按一次",
        "en": "The document was created but could not be saved to the drive. Your entries are kept; please try again shortly.",
        "vi": "Đã tạo tài liệu nhưng không lưu được vào ổ lưu trữ. Dữ liệu vẫn còn trên màn hình, vui lòng thử lại sau.",
        "th": "สร้างเอกสารแล้วแต่บันทึกลงไดรฟ์ไม่สำเร็จ ข้อมูลยังอยู่บนหน้าจอ กรุณาลองใหม่อีกครั้ง",
    },
    # 欄位驗證（main.describe）
    "where": {"zh": "第 {n} 筆的", "en": "Record {n}: ", "vi": "Mục {n}: ", "th": "รายการที่ {n}: "},
    "too_long": {
        "zh": "{where}{label}太長（最多 {n} 字）",
        "en": "{where}{label} is too long (max {n} characters)",
        "vi": "{where}{label} quá dài (tối đa {n} ký tự)",
        "th": "{where}{label}ยาวเกินไป (ไม่เกิน {n} ตัวอักษร)",
    },
    "need_entry": {
        "zh": "請至少新增一筆照片資料",
        "en": "Please add at least one photo record",
        "vi": "Vui lòng thêm ít nhất một mục ảnh",
        "th": "กรุณาเพิ่มรายการรูปภาพอย่างน้อยหนึ่งรายการ",
    },
    "required": {
        "zh": "{where}{label}必填",
        "en": "{where}{label} is required",
        "vi": "{where}{label} là bắt buộc",
        "th": "{where}ต้องกรอก{label}",
    },
    "too_many": {
        "zh": "{label}太多（最多 {n} 筆）",
        "en": "Too many {label} (max {n})",
        "vi": "Quá nhiều {label} (tối đa {n})",
        "th": "{label}มากเกินไป (ไม่เกิน {n})",
    },
    "invalid": {
        "zh": "{where}{label}格式不正確",
        "en": "{where}{label} is not valid",
        "vi": "{where}{label} không hợp lệ",
        "th": "{where}{label}ไม่ถูกต้อง",
    },
}

FIELD_LABELS: dict[str, dict[str, str]] = {
    "zh": {"category": "表單類別", "project_name": "工程", "project_title": "工程名稱", "code": "編號",
           "filename": "檔案名稱", "entries": "照片資料", "date": "日期", "item": "項目",
           "location": "位置", "desc": "說明", "": "資料"},
    "en": {"category": "Form type", "project_name": "Project", "project_title": "Project name", "code": "No.",
           "filename": "File name", "entries": "photo records", "date": "Date", "item": "Item",
           "location": "Location", "desc": "Notes", "": "Data"},
    "vi": {"category": "Loại biểu mẫu", "project_name": "Công trình", "project_title": "Tên công trình",
           "code": "Số hiệu", "filename": "Tên tệp", "entries": "mục ảnh", "date": "Ngày", "item": "Hạng mục",
           "location": "Vị trí", "desc": "Ghi chú", "": "Dữ liệu"},
    "th": {"category": "ประเภทแบบฟอร์ม", "project_name": "โครงการ", "project_title": "ชื่อโครงการ", "code": "เลขที่",
           "filename": "ชื่อไฟล์", "entries": "รายการรูปภาพ", "date": "วันที่", "item": "รายการ",
           "location": "ตำแหน่ง", "desc": "หมายเหตุ", "": "ข้อมูล"},
}


def text(key: str, **params) -> dict[str, str]:
    """{語言: 訊息}。params 的值可以是字串，也可以是 {語言: 字串}（例：欄位名稱）。"""
    out = {}
    for lang in LANGS:
        values = {k: (v[lang] if isinstance(v, dict) else v) for k, v in params.items()}
        out[lang] = MESSAGES[key][lang].format(**values)
    return out


def label(field: str) -> dict[str, str]:
    return {lang: FIELD_LABELS[lang].get(field, field) for lang in LANGS}


def body(texts: dict[str, str]) -> dict[str, str]:
    """JSON 回應：detail 是中文（舊前端和 log 用），其他語言放 detail_<語言>。"""
    out = {"detail": texts["zh"]}
    out.update({f"detail_{lang}": texts[lang] for lang in LANGS if lang != "zh"})
    return out
