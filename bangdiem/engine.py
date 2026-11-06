"""Bộ máy quy trình "Xét duyệt và cấp phát bảng điểm (TO-BE)".

Mỗi hàm nghiệp vụ ứng với một (hoặc một chuỗi) phần tử của mô hình BPMN to-be đã sửa.
Hàm ghi mã phần tử vào ``request["history"]`` để giao diện tô sáng đúng bước.

Module thuần Python, không phụ thuộc Flask hay SQLite: kiểm thử được độc lập
(xem ``tests/test_scenarios.py``). Lớp lưu trữ (``store.py``) nạp/ghi đối tượng ``Db``.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .bpmn import CANCELLABLE, STATUS, STEPS, step_type

DAY = 86_400_000
HOUR = 3_600_000
VN_TZ = timezone(timedelta(hours=7))

DEFAULT_SCALE = [
    {"letter": "A", "min": 8.5, "gpa": 4.0},
    {"letter": "B+", "min": 7.8, "gpa": 3.5},
    {"letter": "B", "min": 7.0, "gpa": 3.0},
    {"letter": "C+", "min": 6.3, "gpa": 2.5},
    {"letter": "C", "min": 5.5, "gpa": 2.0},
    {"letter": "D+", "min": 4.8, "gpa": 1.5},
    {"letter": "D", "min": 4.0, "gpa": 1.0},
    {"letter": "F", "min": 0.0, "gpa": 0.0},
]

DEFAULT_CONFIG = {
    "nameSimilarityThreshold": 0.85,  # ngưỡng khớp họ tên (0..1)
    "confidenceThreshold": 0.90,  # ngưỡng độ tin cậy đối chiếu điểm, đạt thì không qua Khoa
    "errorPenalty": 0.25,  # trừ độ tin cậy cho mỗi lỗi
    "warningPenalty": 0.12,  # trừ độ tin cậy cho mỗi dấu hiệu bất thường
    "outlierGap": 3.5,  # lệch so với điểm TB của SV từ mức này trở lên = bất thường
    "supplementDays": 3,
    "khoaRemindDays": 2,
    "ppRemindDays": 1,
    "maxCopies": 10,
    "emailDomain": "due.udn.vn",
    "signerName": "ThS. Lê Thị Phó Phòng",
    "scale": DEFAULT_SCALE,
}


class ProcessError(Exception):
    """Vi phạm luật nghiệp vụ hoặc thao tác không đúng bước (HTTP 409/400)."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class Db:
    """Trạng thái hệ thống trong bộ nhớ. ``store.py`` nạp/ghi đối tượng này vào SQLite."""

    def __init__(self, fixed_now: int | None = None):
        self.config: dict = copy.deepcopy(DEFAULT_CONFIG)
        self.students: list[dict] = []
        self.grades: list[dict] = []
        self.requests: list[dict] = []
        self.outbox: list[dict] = []
        self.logs: list[dict] = []
        self.issuance: list[dict] = []
        self.archive: list[dict] = []
        self.seq = {"req": 0, "mail": 0, "grade": 0, "log": 0}
        self.clock_offset = 0  # độ lệch đồng hồ mô phỏng (ms) để thử các timer
        self.fixed_now = fixed_now  # dùng trong kiểm thử
        self.fault = False  # giả lập sự cố CSDL điểm (nhánh lỗi truy xuất)
        # Không lưu: dịch vụ ngoài được gắn khi chạy
        self.signer = None  # bangdiem.signing.Signer
        self.on_email: Callable[[dict], None] | None = None
        self.store_connection = None


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
def jround(x: float, d: int = 2) -> float:
    """Làm tròn nửa lên như Math.round của JavaScript."""
    f = 10 ** d
    return math.floor(x * f + 0.5) / f


def is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isnan(v)


def to_num(v: Any) -> int | float | None:
    """Chuỗi -> số (chấp nhận dấu phẩy thập phân). Rỗng/không hợp lệ -> None."""
    if v is None:
        return None
    if is_num(v):
        return int(v) if float(v).is_integer() else v
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return int(f) if f.is_integer() else f


def strip_diacritics(s: Any) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = re.sub(r"[̀-ͯ]", "", s)
    return s.replace("đ", "d").replace("Đ", "D")


def norm_space(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ratio(a: str, b: str) -> float:
    n = max(len(a), len(b)) or 1
    return 1 - levenshtein(a, b) / n


def name_similarity(a: str, b: str) -> float:
    """Độ giống hai họ tên (0..1): 70% so khớp không dấu + 30% so khớp có dấu."""
    x, y = norm_space(a).lower(), norm_space(b).lower()
    return jround(0.7 * ratio(strip_diacritics(x), strip_diacritics(y)) + 0.3 * ratio(x, y), 3)


def norm_date(s: Any) -> str:
    """Chuẩn hóa ngày về yyyy-mm-dd (chấp nhận dd/mm/yyyy, d-m-yyyy, yyyy-mm-dd)."""
    s = str(s or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", s)
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    return s


def parse_score(v: Any):
    """Điểm hệ 10: số, None (trống) hoặc giữ nguyên chuỗi nếu không phải số (để luật D2 bắt)."""
    if v is None:
        return None
    if is_num(v):
        return float(v)
    s = str(v).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return str(v)


def letter_of(score: float, scale: list | None = None) -> dict:
    sc = sorted(scale or DEFAULT_SCALE, key=lambda x: -x["min"])
    r = jround(score, 1)  # điểm học phần làm tròn 1 chữ số
    for s in sc:
        if r >= s["min"]:
            return s
    return sc[-1]


def canonical(v: Any) -> str:
    """JSON có thứ tự khóa cố định để băm ổn định."""
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def code_of(h: str) -> str:
    c = h[:12].upper()
    return f"{c[0:4]}-{c[4:8]}-{c[8:12]}"


def transcript_hash(tr: dict) -> str:
    return sha256(canonical(tr))


# ---------------------------------------------------------------------------
# Đồng hồ, nhật ký, email
# ---------------------------------------------------------------------------
def now(db: Db) -> int:
    base = db.fixed_now if db.fixed_now is not None else int(time.time() * 1000)
    return base + (db.clock_offset or 0)


def advance_clock(db: Db, ms: int) -> list[dict]:
    db.clock_offset = (db.clock_offset or 0) + int(ms)
    return tick(db)


def sys_log(db: Db, level: str, msg: str, req_id: str | None = None, actor: str | None = None) -> None:
    db.seq["log"] += 1
    db.logs.append({"id": db.seq["log"], "t": now(db), "level": level, "msg": msg, "reqId": req_id, "actor": actor})


def find_student(db: Db, mssv: Any) -> dict | None:
    mssv = str(mssv or "").strip()
    return next((s for s in db.students if s["mssv"] == mssv), None)


def grades_of(db: Db, mssv: str) -> list[dict]:
    return [g for g in db.grades if g["mssv"] == mssv]


def get_req(db: Db, rid: str) -> dict:
    r = next((x for x in db.requests if x["id"] == rid), None)
    if not r:
        raise ProcessError(f"Không tìm thấy yêu cầu {rid}", 404)
    return r


def require_status(req: dict, *allowed: str) -> None:
    if req["status"] not in allowed:
        raise ProcessError(
            f'Yêu cầu {req["id"]} đang ở trạng thái "{STATUS[req["status"]]["label"]}", không thực hiện được thao tác này.'
        )


def trace(db: Db, req: dict, step: str, actor: str | None, note: str = "", kind: str | None = None) -> None:
    req["history"].append({"t": now(db), "step": step, "actor": actor or "Hệ thống", "note": note or "", "kind": kind or step_type(step)})


def set_status(db: Db, req: dict, status: str) -> None:
    req["status"] = status
    req["updatedAt"] = now(db)


def send_email(db: Db, req: dict | None, step: str, to: str, to_role: str, subject: str, body: str) -> dict:
    db.seq["mail"] += 1
    m = {
        "id": db.seq["mail"], "t": now(db), "to": to, "toRole": to_role, "subject": subject, "body": body,
        "reqId": req["id"] if req else None, "step": step, "delivery": "outbox",
    }
    db.outbox.append(m)
    if db.on_email:
        db.on_email(m)  # gửi SMTP thật nếu được cấu hình (mailer.py)
    return m


def dept_mailbox(db: Db, khoa: str | None) -> str:
    slug = re.sub(r"[^a-z]+", "", strip_diacritics(khoa or "khoa").lower())
    return f"vpk.{slug}@{db.config['emailDomain']}"


# ---------------------------------------------------------------------------
# Nhập dữ liệu
# ---------------------------------------------------------------------------
def _pick(d: dict, *keys: str, default: Any = "") -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def norm_student(s: dict) -> dict:
    return {
        "mssv": str(_pick(s, "mssv", "MSSV")).strip(),
        "hoTen": norm_space(_pick(s, "hoTen", "ho_ten", "Họ tên")),
        "ngaySinh": norm_date(_pick(s, "ngaySinh", "ngay_sinh")),
        "gioiTinh": norm_space(_pick(s, "gioiTinh", "gioi_tinh")),
        "lop": norm_space(_pick(s, "lop")),
        "khoa": norm_space(_pick(s, "khoa")),
        "nganh": norm_space(_pick(s, "nganh")),
        "khoaHoc": norm_space(_pick(s, "khoaHoc", "khoa_hoc")),
        "email": norm_space(_pick(s, "email")).lower(),
        "trangThai": norm_space(_pick(s, "trangThai", "trang_thai")) or "Đang học",
    }


def norm_grade(db: Db, g: dict) -> dict:
    db.seq["grade"] += 1
    return {
        "id": f"g{db.seq['grade']}",
        "mssv": str(_pick(g, "mssv")).strip(),
        "namHoc": norm_space(_pick(g, "namHoc", "nam_hoc")),
        "hocKy": norm_space(_pick(g, "hocKy", "hoc_ky")),
        "maHP": norm_space(_pick(g, "maHP", "ma_hp")),
        "tenHP": norm_space(_pick(g, "tenHP", "ten_hp")),
        "soTC": to_num(_pick(g, "soTC", "so_tc", default=None)),
        "diem10": parse_score(_pick(g, "diem10", "diem_10", "diem", default=None)),
        "diemChu": norm_space(_pick(g, "diemChu", "diem_chu")).upper(),
    }


def import_students(db: Db, rows: list[dict], mode: str = "merge") -> dict:
    if mode == "replace":
        db.students = []
    added = updated = skipped = 0
    for raw in rows:
        s = norm_student(raw)
        if not s["mssv"]:
            skipped += 1
            continue
        i = next((k for k, x in enumerate(db.students) if x["mssv"] == s["mssv"]), -1)
        if i >= 0:
            db.students[i] = s
            updated += 1
        else:
            db.students.append(s)
            added += 1
    sys_log(db, "info", f"Nhập CSDL sinh viên: thêm {added}, cập nhật {updated}, bỏ qua {skipped}")
    return {"added": added, "updated": updated, "skipped": skipped}


def import_grades(db: Db, rows: list[dict], mode: str = "merge") -> dict:
    skipped = 0
    out = []
    for raw in rows:
        g = norm_grade(db, raw)
        if not g["mssv"]:
            skipped += 1
            continue
        out.append(g)
    if mode == "replace":
        db.grades = []
    else:  # gộp: thay toàn bộ điểm của các MSSV có trong tệp
        ids = {g["mssv"] for g in out}
        db.grades = [g for g in db.grades if g["mssv"] not in ids]
    db.grades.extend(out)
    sys_log(db, "info", f"Nhập CSDL điểm: {len(out)} dòng điểm, bỏ qua {skipped}")
    return {"added": len(out), "skipped": skipped}


# ---------------------------------------------------------------------------
# Quy trình
# ---------------------------------------------------------------------------
def submit_request(db: Db, form: dict, actor: str | None = None) -> dict:
    """s_start → s_task → g_m1 → ca_xt ... (Sinh viên gửi yêu cầu)."""
    db.seq["req"] += 1
    year = datetime.fromtimestamp(now(db) / 1000, VN_TZ).year
    ban_giay = bool(form.get("banGiay"))
    so_ban = to_num(form.get("soBan") or 1) if ban_giay else 0
    req = {
        "id": f"BD{year}-{db.seq['req']:04d}",
        "createdAt": now(db), "updatedAt": now(db), "status": None,
        "form": {
            "mssv": str(form.get("mssv") or "").strip(),
            "hoTen": norm_space(form.get("hoTen")),
            "ngaySinh": norm_date(form.get("ngaySinh")),
            "email": norm_space(form.get("email")).lower(),
            "sdt": re.sub(r"[\s.]", "", str(form.get("sdt") or "")),
            "mucDich": norm_space(form.get("mucDich")),
            "ngonNgu": "en" if form.get("ngonNgu") == "en" else "vi",
            "banGiay": ban_giay,
            "soBan": so_ban,
            "ghiChu": norm_space(form.get("ghiChu")),
        },
        "options": {"ghiChuBangDiem": "", "signer": db.config["signerName"], "hiddenSemesters": []},
        "history": [], "validation": None, "check": None, "acks": [], "transcript": None,
        "transcriptVersions": 0, "autoChecks": [], "feedback": [], "signature": None, "timers": {},
        "paper": {"printedAt": None, "stampedAt": None, "deliveredAt": None, "receiver": None},
        "branches": None, "decisionNote": "", "attempts": 0, "approvedBy": None, "studentSnapshot": None,
    }
    db.requests.append(req)
    who = actor or req["form"]["hoTen"] or req["form"]["mssv"]
    trace(db, req, "s_start", who, "Sinh viên phát sinh nhu cầu bảng điểm")
    trace(db, req, "s_task", who, f"Đăng nhập SSO ({req['form']['mssv']}) và gửi yêu cầu: {req['form']['mucDich'] or '—'}")
    trace(db, req, "g_m1", "Hệ thống", "Tiếp nhận yêu cầu mới")
    sys_log(db, "info", f"Tiếp nhận yêu cầu {req['id']} của {req['form']['mssv']}", req["id"], who)
    run_validation(db, req)
    return req


def validate_form(db: Db, form: dict) -> dict:
    """ca_xt: 8 luật X1–X8, so khớp họ tên theo ngưỡng."""
    cfg = db.config
    items: list[dict] = []

    def add(code: str, field: str, ok: bool, msg: str) -> None:
        items.append({"code": code, "field": field, "ok": bool(ok), "msg": msg})

    st = find_student(db, form.get("mssv"))
    add("X1", "mssv", st is not None,
        "MSSV có trong CSDL sinh viên" if st else f'MSSV "{form.get("mssv")}" không có trong CSDL sinh viên')
    sim = None
    if st:
        sim = name_similarity(form.get("hoTen", ""), st["hoTen"])
        thr = cfg["nameSimilarityThreshold"]
        ok = sim >= thr
        add("X2", "hoTen", ok,
            f"Họ tên khớp CSDL (độ giống {round(sim * 100)}%)" if ok
            else f'Họ tên "{form.get("hoTen")}" không khớp CSDL (độ giống {round(sim * 100)}% < ngưỡng {round(thr * 100)}%)')
        dob_ok = norm_date(form.get("ngaySinh")) == st["ngaySinh"]
        add("X3", "ngaySinh", dob_ok, "Ngày sinh khớp CSDL" if dob_ok else "Ngày sinh không khớp CSDL sinh viên")
        active = st["trangThai"] != "Đã xóa tên"
        add("X6", "mssv", active,
            f"Tình trạng học tập: {st['trangThai']}" if active else "Sinh viên đã bị xóa tên, cần liên hệ Phòng Đào tạo")
    email = form.get("email") or ""
    email_ok = re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) is not None
    owned = email_ok and st is not None and (email == st["email"] or email.endswith("@" + cfg["emailDomain"]))
    add("X4", "email", owned,
        "Email không đúng định dạng" if not email_ok
        else "Email nhận bảng điểm hợp lệ" if owned
        else f"Email phải là email đăng ký trong CSDL hoặc email @{cfg['emailDomain']}")
    phone_ok = re.fullmatch(r"0[0-9]{9}", form.get("sdt") or "") is not None
    add("X5", "sdt", phone_ok, "Số điện thoại hợp lệ" if phone_ok else "Số điện thoại phải gồm 10 chữ số, bắt đầu bằng 0")
    purpose_ok = len(form.get("mucDich") or "") >= 5
    add("X7", "mucDich", purpose_ok,
        "Đã nêu mục đích sử dụng" if purpose_ok else "Cần nêu rõ mục đích sử dụng bảng điểm (ít nhất 5 ký tự)")
    if form.get("banGiay"):
        n = form.get("soBan")
        ok = isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= cfg["maxCopies"]
        add("X8", "soBan", ok, f"Số bản giấy: {n}" if ok else f"Số bản giấy phải từ 1 đến {cfg['maxCopies']}")
    return {"valid": all(i["ok"] for i in items), "items": items, "nameSimilarity": sim, "studentFound": st is not None}


def run_validation(db: Db, req: dict) -> dict:
    req["attempts"] += 1
    v = validate_form(db, req["form"])
    req["validation"] = {**v, "at": now(db)}
    failed = [i for i in v["items"] if not i["ok"]]
    trace(db, req, "ca_xt", "Hệ thống", f"Đối chiếu CSDL sinh viên: {len(v['items']) - len(failed)}/{len(v['items'])} tiêu chí đạt")
    if not v["valid"]:
        trace(db, req, "g_hl", "Hệ thống", "Không hợp lệ")
        st = find_student(db, req["form"]["mssv"])
        lines = "\n".join("• " + f["msg"] for f in failed)
        send_email(
            db, req, "Activity_0ze94gf", req["form"]["email"] or (st or {}).get("email") or "(không có email)", "SV",
            f"[{req['id']}] Yêu cầu bổ sung thông tin cấp bảng điểm",
            f"Chào bạn,\n\nYêu cầu cấp bảng điểm {req['id']} chưa hợp lệ vì:\n{lines}\n\n"
            f"Vui lòng đăng nhập hệ thống và bổ sung trong vòng {db.config['supplementDays']} ngày. "
            "Quá hạn, yêu cầu sẽ tự động bị hủy.\n\nPhòng Đào tạo",
        )
        trace(db, req, "Activity_0ze94gf", "Hệ thống", f"Đã gửi email yêu cầu bổ sung ({len(failed)} mục)")
        set_status(db, req, "CHO_BO_SUNG")
        req["timers"]["supplementDue"] = now(db) + db.config["supplementDays"] * DAY
        return req
    trace(db, req, "g_hl", "Hệ thống", "Hợp lệ")
    req["studentSnapshot"] = copy.deepcopy(find_student(db, req["form"]["mssv"]))
    return retrieve_grades(db, req)


def supplement(db: Db, rid: str, changes: dict, actor: str | None = None) -> dict:
    """s_bs_task → g_m1 → ca_xt (SV bổ sung thông tin trực tuyến)."""
    req = get_req(db, rid)
    require_status(req, "CHO_BO_SUNG")
    f = req["form"]
    changed = []
    for k in ("hoTen", "ngaySinh", "email", "sdt", "mucDich", "soBan", "banGiay", "ngonNgu", "ghiChu"):
        if k not in changes or changes[k] is None:
            continue
        v = changes[k]
        if k == "ngaySinh":
            v = norm_date(v)
        elif k == "soBan":
            v = to_num(v)
        elif k == "banGiay":
            v = bool(v)
        elif k == "sdt":
            v = re.sub(r"[\s.]", "", str(v))
        elif k == "email":
            v = norm_space(v).lower()
        elif k == "ngonNgu":
            v = "en" if v == "en" else "vi"
        else:
            v = norm_space(v)
        if v != f.get(k):
            f[k] = v
            changed.append(k)
    if not f["banGiay"]:
        f["soBan"] = 0
    req["timers"].pop("supplementDue", None)
    trace(db, req, "s_bs_task", actor or f["hoTen"], f"Bổ sung: {', '.join(changed)}" if changed else "Gửi lại không thay đổi")
    trace(db, req, "g_m1", "Hệ thống", "Gộp yêu cầu bổ sung vào luồng xác thực")
    return run_validation(db, req)


def _term_key(r: dict) -> str:
    return f"{r['hocKy']} {r['namHoc']}"


def retrieve_grades(db: Db, req: dict) -> dict:
    """t_truyxuat (đa thể hiện theo học kỳ) → g_mdc → t_doichieu; lỗi → Boundary_LoiTruyXuat."""
    if db.fault:
        trace(db, req, "t_truyxuat", "Hệ thống", "Không kết nối được CSDL điểm (sự cố giả lập)")
        return retrieval_failed(db, req, "Không kết nối được CSDL điểm")
    rows = grades_of(db, req["form"]["mssv"])
    terms = {(r["namHoc"], r["hocKy"]) for r in rows}
    trace(db, req, "t_truyxuat", "Hệ thống",
          f"Truy xuất {len(rows)} dòng điểm, {len(terms)} học kỳ (mỗi học kỳ một lượt truy xuất)")
    trace(db, req, "g_mdc", "Hệ thống", "")
    return reconcile(db, req)


def retrieval_failed(db: Db, req: dict, reason: str) -> dict:
    """Boundary_LoiTruyXuat → Task_GhiNhanLoiTruyXuat → Task_ThongBaoLoiTruyXuat → End_LoiHeThong."""
    trace(db, req, "Boundary_LoiTruyXuat", "Hệ thống", reason, "error")
    sys_log(db, "error", f"Sự cố truy xuất điểm cho yêu cầu {req['id']}: {reason}", req["id"])
    trace(db, req, "Task_GhiNhanLoiTruyXuat", "Hệ thống", "Đã ghi nhận sự cố vào nhật ký hệ thống")
    send_email(
        db, req, "Task_ThongBaoLoiTruyXuat", req["form"]["email"], "SV",
        f"[{req['id']}] Hệ thống tạm thời chưa truy xuất được điểm",
        f"Chào bạn,\n\nYêu cầu {req['id']} chưa xử lý được do sự cố khi truy xuất CSDL điểm.\n"
        "Phòng Đào tạo đã ghi nhận sự cố. Bạn vui lòng gửi lại yêu cầu sau ít phút.\n\nPhòng Đào tạo",
    )
    trace(db, req, "Task_ThongBaoLoiTruyXuat", "Hệ thống", "Đã gửi email đề nghị sinh viên thử lại sau")
    set_status(db, req, "LOI_HE_THONG")
    req["decisionNote"] = reason
    trace(db, req, "End_LoiHeThong", "Hệ thống", "Dừng do lỗi hệ thống")
    return req


def check_grades(db: Db, mssv: str, acks: list[str] | None = None) -> dict:
    """Luật đối chiếu điểm D0–D7, phát hiện bất thường A1 và chấm độ tin cậy."""
    cfg = db.config
    acks = acks or []
    rows = grades_of(db, mssv)
    errors: list[dict] = []
    warnings: list[dict] = []
    infos: list[dict] = []
    if not rows:
        errors.append({"code": "D0", "gradeId": None, "msg": "Không có dữ liệu điểm của sinh viên trong CSDL điểm"})
    dup: dict[str, list[dict]] = {}
    for r in rows:
        label = f"{r['maHP'] or '?'} – {r['tenHP'] or '?'} ({r['hocKy']} {r['namHoc']})"
        if not r["maHP"] or not r["tenHP"]:
            errors.append({"code": "D7", "gradeId": r["id"], "msg": f"Thiếu mã hoặc tên học phần: {label}"})
        d = r["diem10"]
        if d is None or d == "":
            errors.append({"code": "D1", "gradeId": r["id"], "msg": f"Thiếu điểm học phần {label}"})
        elif not is_num(d) or d < 0 or d > 10:
            errors.append({"code": "D2", "gradeId": r["id"], "msg": f'Điểm "{d}" ngoài thang 0–10: {label}'})
        else:
            exp = letter_of(d, cfg["scale"])["letter"]
            if r["diemChu"] and r["diemChu"] != exp:
                errors.append({"code": "D3", "gradeId": r["id"],
                               "msg": f"Điểm chữ {r['diemChu']} không khớp điểm số {fmt_num(d)} (đúng là {exp}): {label}"})
        tc = r["soTC"]
        if not (isinstance(tc, int) and not isinstance(tc, bool) and 1 <= tc <= 10):
            errors.append({"code": "D4", "gradeId": r["id"],
                           "msg": f"Số tín chỉ không hợp lệ ({'trống' if tc is None else fmt_num(tc)}): {label}"})
        dup.setdefault(f"{r['namHoc']}|{r['hocKy']}|{r['maHP']}", []).append(r)
    for lst in dup.values():
        if len(lst) > 1:
            r = lst[1]
            errors.append({"code": "D5", "gradeId": r["id"],
                           "msg": f"Học phần {r['maHP']} bị nhập trùng {len(lst)} lần trong {r['hocKy']} {r['namHoc']}"})
    # Học lại / cải thiện: cùng học phần ở nhiều học kỳ — chỉ ghi chú, lấy điểm cao nhất
    by_course: dict[str, set] = {}
    for r in rows:
        by_course.setdefault(r["maHP"], set()).add(r["namHoc"] + r["hocKy"])
    for c, s in by_course.items():
        if len(s) > 1:
            infos.append({"code": "I1", "msg": f"Học phần {c} học {len(s)} lần, lấy điểm cao nhất"})
    # Bất thường: điểm lệch xa điểm trung bình của chính sinh viên
    valid = [r for r in rows if is_num(r["diem10"]) and 0 <= r["diem10"] <= 10]
    if len(valid) >= 6:
        mean = sum(r["diem10"] for r in valid) / len(valid)
        for r in valid:
            key = "A1|" + r["id"]
            gap = abs(r["diem10"] - mean)
            if gap >= cfg["outlierGap"] and key not in acks:
                warnings.append({"code": "A1", "key": key, "gradeId": r["id"],
                                 "msg": f"Điểm {fmt_num(r['diem10'])} của {r['maHP']} lệch {jround(gap, 1)} so với điểm TB "
                                        f"{jround(mean, 1)} của SV — cần Khoa xác nhận"})
    confidence = max(0.0, jround(1 - len(errors) * cfg["errorPenalty"] - len(warnings) * cfg["warningPenalty"], 2))
    passed = not errors and confidence >= cfg["confidenceThreshold"]
    return {"rows": len(rows), "errors": errors, "warnings": warnings, "infos": infos,
            "confidence": confidence, "threshold": cfg["confidenceThreshold"], "pass": passed}


def grade_review_assistance(check: dict) -> dict:
    """Create read-only review suggestions from existing deterministic grade checks."""
    guidance = {
        "D0": "Kiểm tra việc nhập đúng MSSV và xác nhận dữ liệu đã được đồng bộ từ nguồn điểm chính thức.",
        "D1": "Đối chiếu học phần với bảng điểm gốc để xác định điểm đang thiếu hay chưa được cập nhật.",
        "D2": "Đối chiếu điểm với nguồn điểm chính thức; không tự sửa hoặc suy đoán giá trị thay thế.",
        "D3": "Kiểm tra quy tắc quy đổi điểm chữ và đối chiếu điểm số với nguồn chính thức trước khi hiệu chỉnh.",
        "D4": "Đối chiếu số tín chỉ với chương trình đào tạo hoặc danh mục học phần đã được phê duyệt.",
        "D5": "So sánh các dòng trùng với bảng điểm gốc và lịch sử nhập; chỉ xử lý sau khi Khoa xác nhận.",
        "D7": "Tra cứu mã và tên học phần trong danh mục đào tạo; xác minh với nguồn chính thức nếu vẫn chưa rõ.",
        "A1": "Đây chỉ là dấu hiệu lệch so với điểm trung bình, không chứng minh điểm sai. Hãy đối chiếu nguồn chính thức và ghi nhận quyết định của Khoa.",
        "I1": "Xác minh đây là học lại/cải thiện hợp lệ và áp dụng quy định tính điểm hiện hành.",
    }
    findings = []
    for level in ("errors", "warnings", "infos"):
        severity = {"errors": "error", "warnings": "warning", "infos": "info"}[level]
        for item in check.get(level, []):
            code = item.get("code", "")
            findings.append({
                "severity": severity,
                "code": code,
                "gradeId": item.get("gradeId"),
                "message": item.get("msg", ""),
                "suggestion": guidance.get(
                    code, "Đối chiếu thông tin với hồ sơ nguồn và áp dụng quy trình nghiệp vụ hiện hành."
                ),
            })
    return {
        "method": "local-rules",
        "readOnly": True,
        "humanDecisionRequired": True,
        "summary": (
            f"{len(check.get('errors', []))} lỗi, {len(check.get('warnings', []))} dấu hiệu cần xác minh, "
            f"{len(check.get('infos', []))} ghi chú."
        ),
        "findings": findings,
        "limitations": (
            "Gợi ý được tạo bằng luật D0-D7/A1/I1 từ CSDL hiện có; hệ thống không truy cập sổ điểm gốc, "
            "không xác định nguyên nhân thay con người và không tự sửa dữ liệu."
        ),
    }


def fmt_num(x: Any) -> str:
    if is_num(x) and float(x).is_integer():
        return str(int(x))
    return str(x)


def reconcile(db: Db, req: dict) -> dict:
    """t_doichieu → g_diem."""
    c = check_grades(db, req["form"]["mssv"], req["acks"])
    req["check"] = {**c, "at": now(db)}
    trace(db, req, "t_doichieu", "Hệ thống",
          f"{len(c['errors'])} lỗi, {len(c['warnings'])} bất thường, độ tin cậy {round(c['confidence'] * 100)}% "
          f"(ngưỡng {round(c['threshold'] * 100)}%)")
    if c["pass"]:
        trace(db, req, "g_diem", "Hệ thống", "Có — điểm đầy đủ, chính xác")
        trace(db, req, "g_m2", "Hệ thống", "")
        return create_transcript(db, req)
    trace(db, req, "g_diem", "Hệ thống", "Không — chuyển Khoa rà soát")
    set_status(db, req, "CHO_KHOA")
    req["timers"]["khoaRemindAt"] = now(db) + db.config["khoaRemindDays"] * DAY
    req["timers"]["khoaReminded"] = False
    return req


def khoa_edit_grade(db: Db, rid: str, grade_id: str, patch: dict, actor: str) -> dict:
    """t_khoa: Khoa hiệu chỉnh 1 dòng điểm (ghi thẳng CSDL điểm, có nhật ký kiểm toán)."""
    req = get_req(db, rid)
    require_status(req, "CHO_KHOA")
    g = next((x for x in db.grades if x["id"] == grade_id and x["mssv"] == req["form"]["mssv"]), None)
    if not g:
        raise ProcessError("Không tìm thấy dòng điểm", 404)
    before = dict(g)
    if patch.get("delete"):
        db.grades = [x for x in db.grades if x is not g]
        trace(db, req, "t_khoa", actor, f"Xóa dòng điểm trùng {before['maHP']} ({before['hocKy']} {before['namHoc']})")
        sys_log(db, "audit", f"{actor} xóa dòng điểm {before['maHP']} của {before['mssv']}", rid, actor)
        return req
    if "diem10" in patch:
        g["diem10"] = parse_score(patch["diem10"])
    if "diemChu" in patch and patch["diemChu"] is not None:
        g["diemChu"] = norm_space(patch["diemChu"]).upper()
    if patch.get("autoLetter") and is_num(g["diem10"]):
        g["diemChu"] = letter_of(g["diem10"], db.config["scale"])["letter"]
    if "soTC" in patch:
        g["soTC"] = to_num(patch["soTC"])
    if patch.get("tenHP") is not None:
        g["tenHP"] = norm_space(patch["tenHP"])
    if patch.get("maHP") is not None:
        g["maHP"] = norm_space(patch["maHP"])
    diff = [f"{k}: {fmt_num(before[k]) if before[k] is not None else '∅'} → {fmt_num(g[k]) if g[k] is not None else '∅'}"
            for k in ("diem10", "diemChu", "soTC", "tenHP", "maHP") if before[k] != g[k]]
    trace(db, req, "t_khoa", actor, f"Hiệu chỉnh {g['maHP']}: {'; '.join(diff) or 'không đổi'}")
    sys_log(db, "audit", f"{actor} hiệu chỉnh điểm {g['maHP']} của {g['mssv']}: {'; '.join(diff)}", rid, actor)
    return req


def khoa_acknowledge(db: Db, rid: str, key: str, actor: str) -> dict:
    """Khoa xác nhận một điểm bất thường là đúng thực tế."""
    req = get_req(db, rid)
    require_status(req, "CHO_KHOA")
    if key not in req["acks"]:
        req["acks"].append(key)
    trace(db, req, "t_khoa", actor, "Xác nhận điểm bất thường là đúng thực tế")
    return req


def khoa_decide(db: Db, rid: str, can_fix: bool, note: str, actor: str) -> dict:
    """g_kh: Có → g_mdc → t_doichieu; Không → end_kh."""
    req = get_req(db, rid)
    require_status(req, "CHO_KHOA")
    req["timers"].pop("khoaRemindAt", None)
    if can_fix:
        trace(db, req, "g_kh", actor, "Có — đã hiệu chỉnh" + (f": {note}" if note else ""))
        trace(db, req, "g_mdc", "Hệ thống", "Đối chiếu lại sau hiệu chỉnh")
        return reconcile(db, req)
    trace(db, req, "g_kh", actor, "Không hiệu chỉnh được")
    req["decisionNote"] = norm_space(note) or "Khoa không thể hiệu chỉnh dữ liệu điểm"
    set_status(db, req, "KHOA_TU_CHOI")
    send_email(
        db, req, "end_kh", req["form"]["email"], "SV", f"[{req['id']}] Từ chối cấp bảng điểm",
        f"Chào bạn,\n\nKhoa không thể hiệu chỉnh dữ liệu điểm nên yêu cầu {req['id']} bị từ chối.\n"
        f"Lý do: {req['decisionNote']}\n\nVui lòng liên hệ văn phòng Khoa để được hỗ trợ.\n\nPhòng Đào tạo",
    )
    trace(db, req, "end_kh", actor, req["decisionNote"])
    sys_log(db, "warn", f"Khoa từ chối yêu cầu {req['id']}", req["id"], actor)
    return req


# ------------------------- Bảng điểm & GPA -------------------------
def term_order(r: dict) -> int:
    y = re.match(r"\d{1,4}", str(r["namHoc"]))
    k = re.sub(r"\D", "", str(r["hocKy"]))
    return (int(y.group(0)) if y else 0) * 10 + (int(k) if k else 0)


def classify(g: float) -> str:
    if g >= 3.6:
        return "Xuất sắc"
    if g >= 3.2:
        return "Giỏi"
    if g >= 2.5:
        return "Khá"
    if g >= 2.0:
        return "Trung bình"
    return "Yếu"


def compute_summary(rows: list[dict], scale: list | None = None) -> dict:
    """Học lại lấy điểm cao nhất; tín chỉ tích lũy chỉ tính học phần đạt (≥ 4.0)."""
    best: dict[str, dict] = {}
    for r in rows:
        if not is_num(r.get("diem10")):
            continue
        if r["maHP"] not in best or r["diem10"] > best[r["maHP"]]["diem10"]:
            best[r["maHP"]] = r
    tc = sum4 = sum10 = tc_pass = 0
    for r in best.values():
        n = r["soTC"] if is_num(r.get("soTC")) else 0
        s = letter_of(r["diem10"], scale)
        tc += n
        sum4 += s["gpa"] * n
        sum10 += r["diem10"] * n
        if r["diem10"] >= 4.0:
            tc_pass += n
    gpa4 = jround(sum4 / tc, 2) if tc else 0
    return {"gpa4": gpa4, "gpa10": jround(sum10 / tc, 2) if tc else 0, "tcTichLuy": tc_pass, "tcDangKy": tc,
            "xepLoai": classify(gpa4)}


def build_transcript(db: Db, req: dict) -> dict:
    st = find_student(db, req["form"]["mssv"])
    scale = db.config["scale"]
    rows = sorted(grades_of(db, req["form"]["mssv"]), key=lambda r: (term_order(r), r["maHP"]))
    hidden = req["options"].get("hiddenSemesters") or []
    terms: list[dict] = []
    for r in rows:
        key = _term_key(r)
        if key in hidden:
            continue
        t = next((x for x in terms if x["key"] == key), None)
        if not t:
            t = {"key": key, "hocKy": r["hocKy"], "namHoc": r["namHoc"], "rows": []}
            terms.append(t)
        d = r["diem10"] if is_num(r["diem10"]) else 0
        s = letter_of(d, scale)
        t["rows"].append({"maHP": r["maHP"], "tenHP": r["tenHP"], "soTC": r["soTC"], "diem10": r["diem10"],
                          "diemChu": s["letter"], "diem4": s["gpa"]})
    for t in terms:
        tc = sum(x["soTC"] or 0 for x in t["rows"])
        t["tc"] = tc
        t["gpa4"] = jround(sum(x["diem4"] * (x["soTC"] or 0) for x in t["rows"]) / tc, 2) if tc else 0
    included = [r for r in rows if _term_key(r) not in hidden]
    return {
        "requestId": req["id"], "version": req["transcriptVersions"], "createdAt": now(db), "lang": req["form"]["ngonNgu"],
        "student": {k: st[k] for k in ("mssv", "hoTen", "ngaySinh", "gioiTinh", "lop", "khoa", "nganh", "khoaHoc", "trangThai")},
        "semesters": terms, "summary": compute_summary(included, scale),
        "ghiChu": req["options"].get("ghiChuBangDiem") or "",
        "signer": req["options"].get("signer") or db.config["signerName"], "mucDich": req["form"]["mucDich"],
    }


def create_transcript(db: Db, req: dict) -> dict:
    """t_tao → g_dat (chờ chuyên viên PĐT kiểm tra)."""
    req["transcriptVersions"] += 1
    tr = build_transcript(db, req)
    req["transcript"] = tr
    st = find_student(db, req["form"]["mssv"])
    hidden = req["options"].get("hiddenSemesters") or []
    all_terms = {_term_key(r) for r in grades_of(db, req["form"]["mssv"])}
    recomputed = compute_summary([r for r in grades_of(db, req["form"]["mssv"]) if _term_key(r) not in hidden], db.config["scale"])
    req["autoChecks"] = [
        {"ok": tr["student"]["hoTen"] == st["hoTen"] and tr["student"]["ngaySinh"] == st["ngaySinh"],
         "msg": "Thông tin sinh viên trùng khớp CSDL"},
        {"ok": len(tr["semesters"]) == len(all_terms), "msg": f"Đủ học kỳ ({len(tr['semesters'])}/{len(all_terms)})"},
        {"ok": recomputed["gpa4"] == tr["summary"]["gpa4"], "msg": f"GPA tính lại khớp ({tr['summary']['gpa4']:.2f})"},
        {"ok": tr["lang"] == req["form"]["ngonNgu"],
         "msg": f"Ngôn ngữ đúng yêu cầu ({'Tiếng Anh' if tr['lang'] == 'en' else 'Tiếng Việt'})"},
        {"ok": bool(tr["signer"]), "msg": "Có người ký duyệt"},
    ]
    trace(db, req, "t_tao", "Hệ thống",
          f"Tạo bảng điểm điện tử phiên bản {tr['version']} (GPA {tr['summary']['gpa4']:.2f}, {tr['summary']['tcTichLuy']} TC tích lũy)")
    set_status(db, req, "CHO_KIEM_TRA")
    return req


def qc_decide(db: Db, rid: str, ok: bool, feedback: str, actor: str) -> dict:
    """g_dat: Đạt → t_pd; Chưa đạt → t_chinh."""
    req = get_req(db, rid)
    require_status(req, "CHO_KIEM_TRA")
    if ok:
        trace(db, req, "g_dat", actor, "Đạt")
        set_status(db, req, "CHO_PHE_DUYET")
        req["timers"]["ppRemindAt"] = now(db) + db.config["ppRemindDays"] * DAY
        req["timers"]["ppReminded"] = False
        return req
    fb = norm_space(feedback)
    if not fb:
        raise ProcessError('Cần ghi góp ý khi đánh giá "Chưa đạt"', 400)
    trace(db, req, "g_dat", actor, "Chưa đạt: " + fb)
    req["feedback"].append({"t": now(db), "from": "PĐT", "actor": actor, "text": fb})
    set_status(db, req, "CHO_CHINH_SUA")
    return req


def edit_transcript(db: Db, rid: str, patch: dict, actor: str) -> dict:
    """t_chinh → g_m2 → t_tao."""
    req = get_req(db, rid)
    require_status(req, "CHO_CHINH_SUA")
    o = req["options"]
    changes = []
    if patch.get("ngonNgu") and patch["ngonNgu"] != req["form"]["ngonNgu"]:
        req["form"]["ngonNgu"] = "en" if patch["ngonNgu"] == "en" else "vi"
        changes.append("ngôn ngữ")
    if patch.get("ghiChuBangDiem") is not None and norm_space(patch["ghiChuBangDiem"]) != o.get("ghiChuBangDiem"):
        o["ghiChuBangDiem"] = norm_space(patch["ghiChuBangDiem"])
        changes.append("ghi chú")
    if norm_space(patch.get("signer")) and norm_space(patch.get("signer")) != o.get("signer"):
        o["signer"] = norm_space(patch["signer"])
        changes.append("người ký")
    if isinstance(patch.get("hiddenSemesters"), list) and patch["hiddenSemesters"] != o.get("hiddenSemesters"):
        o["hiddenSemesters"] = [str(x) for x in patch["hiddenSemesters"]]
        changes.append("học kỳ hiển thị")
    trace(db, req, "t_chinh", actor, "Chỉnh: " + ", ".join(changes) if changes else "Tạo lại bảng điểm")
    trace(db, req, "g_m2", "Hệ thống", "")
    return create_transcript(db, req)


def pp_decide(db: Db, rid: str, decision: str, note: str, actor: str) -> dict:
    """t_pd → g_pd: Phê duyệt | Yêu cầu chỉnh sửa | Từ chối."""
    req = get_req(db, rid)
    require_status(req, "CHO_PHE_DUYET")
    note = norm_space(note)
    if decision in ("revise", "reject") and not note:
        raise ProcessError("Cần ghi góp ý chỉnh sửa" if decision == "revise" else "Cần ghi lý do từ chối", 400)
    if decision not in ("approve", "revise", "reject"):
        raise ProcessError("Quyết định không hợp lệ", 400)
    req["timers"].pop("ppRemindAt", None)
    trace(db, req, "t_pd", actor, f"Xem xét bảng điểm phiên bản {req['transcript']['version']}")
    if decision == "approve":
        trace(db, req, "g_pd", actor, "Phê duyệt" + (f": {note}" if note else ""))
        req["approvedBy"] = actor
        return sign_and_dispatch(db, req, actor)
    if decision == "revise":
        trace(db, req, "g_pd", actor, "Yêu cầu chỉnh sửa: " + note)
        req["feedback"].append({"t": now(db), "from": "Phó phòng", "actor": actor, "text": note})
        set_status(db, req, "CHO_CHINH_SUA")
        return req
    trace(db, req, "g_pd", actor, "Từ chối")
    req["decisionNote"] = note
    set_status(db, req, "PP_TU_CHOI")
    send_email(
        db, req, "end_tuchoi", req["form"]["email"], "SV", f"[{req['id']}] Yêu cầu cấp bảng điểm bị từ chối",
        f"Chào bạn,\n\nYêu cầu {req['id']} đã bị Phó phòng Đào tạo từ chối.\nLý do: {note}\n\nPhòng Đào tạo",
    )
    trace(db, req, "end_tuchoi", actor, note)
    return req


def sign_and_dispatch(db: Db, req: dict, actor: str) -> dict:
    """t_dongdau → Gateway_0m52u6m (bao hàm) → t_guidt (+ t_in nếu có bản giấy)."""
    if db.signer is None:
        raise ProcessError("Chưa cấu hình khóa ký số", 500)
    tr = req["transcript"]
    h = transcript_hash(tr)
    sig = db.signer.sign(h)
    code = code_of(h)
    req["signature"] = {"hash": h, "signature": sig, "code": code, "signedAt": now(db), "signer": tr["signer"],
                        "approvedBy": actor, "keyId": db.signer.key_id, "algorithm": db.signer.algorithm}
    db.archive.append({"code": code, "hash": h, "signature": sig, "keyId": db.signer.key_id, "reqId": req["id"],
                       "mssv": req["form"]["mssv"], "signedAt": now(db), "transcript": copy.deepcopy(tr)})
    trace(db, req, "t_dongdau", "Hệ thống", f"Ký số {db.signer.algorithm}, mã xác thực {code}; lưu kho bảng điểm")
    paper = req["form"]["banGiay"]
    trace(db, req, "Gateway_0m52u6m", "Hệ thống", "Bản điện tử + bản giấy" if paper else "Bản điện tử")
    extra = f"\n\nBản giấy ({req['form']['soBan']} bản) đang được in, đóng dấu; bạn sẽ được báo khi nhận." if paper else ""
    send_email(
        db, req, "t_guidt", req["form"]["email"], "SV", f"[{req['id']}] Bảng điểm điện tử đã được cấp",
        f"Chào {tr['student']['hoTen']},\n\nBảng điểm điện tử của bạn đã được ký số.\nMã xác thực: {code}\n"
        f"GPA: {tr['summary']['gpa4']:.2f} / 4.0 — {tr['summary']['tcTichLuy']} tín chỉ tích lũy.\n\n"
        "Đơn vị tiếp nhận có thể tra cứu tính xác thực tại mục \"Tra cứu\" bằng mã trên." + extra + "\n\nPhòng Đào tạo",
    )
    trace(db, req, "t_guidt", "Hệ thống", "Đã gửi bảng điểm điện tử qua email")
    req["branches"] = {"email": True, "paper": not paper}
    if paper:
        set_status(db, req, "CHO_IN")
        return req
    return join_and_finish(db, req)


def print_paper(db: Db, rid: str, actor: str) -> dict:
    req = get_req(db, rid)
    require_status(req, "CHO_IN")
    req["paper"]["printedAt"] = now(db)
    trace(db, req, "t_in", actor, f"In {req['form']['soBan']} bản giấy")
    set_status(db, req, "CHO_DONG_DAU")
    return req


def stamp_paper(db: Db, rid: str, actor: str) -> dict:
    req = get_req(db, rid)
    require_status(req, "CHO_DONG_DAU")
    req["paper"]["stampedAt"] = now(db)
    trace(db, req, "Activity_0xvx345", actor, f"Ký tên, đóng dấu đỏ {req['form']['soBan']} bản")
    set_status(db, req, "CHO_XAC_NHAN_GIAY")
    return req


def confirm_paper(db: Db, rid: str, receiver: str, actor: str) -> dict:
    req = get_req(db, rid)
    require_status(req, "CHO_XAC_NHAN_GIAY")
    req["paper"]["deliveredAt"] = now(db)
    req["paper"]["receiver"] = norm_space(receiver) or req["form"]["hoTen"]
    trace(db, req, "Activity_15aejsy", actor, f"Đã giao bản giấy cho {req['paper']['receiver']}")
    req["branches"]["paper"] = True
    return join_and_finish(db, req)


def join_and_finish(db: Db, req: dict) -> dict:
    """Gateway_198pqrp (gộp bao hàm) → t_nhatky → end_ht."""
    b = req.get("branches") or {}
    if not (b.get("email") and b.get("paper")):
        return req
    trace(db, req, "Gateway_198pqrp", "Hệ thống", "Các nhánh cấp phát đã hoàn tất")
    db.issuance.append({
        "t": now(db), "reqId": req["id"], "mssv": req["form"]["mssv"], "hoTen": req["transcript"]["student"]["hoTen"],
        "code": req["signature"]["code"], "dienTu": True, "soBanGiay": req["form"]["soBan"] if req["form"]["banGiay"] else 0,
        "mucDich": req["form"]["mucDich"], "approvedBy": req["signature"]["approvedBy"],
        "leadTimeH": jround((now(db) - req["createdAt"]) / HOUR, 1),
    })
    trace(db, req, "t_nhatky", "Hệ thống", "Ghi sổ cấp phát")
    set_status(db, req, "HOAN_TAT")
    trace(db, req, "end_ht", "Hệ thống", "Bảng điểm đã được cấp")
    sys_log(db, "info", f"Hoàn tất cấp bảng điểm {req['id']}", req["id"])
    return req


# ------------------- Event sub-process: SV chủ động hủy -------------------
def student_cancel(db: Db, rid: str, reason: str, actor: str) -> dict:
    """Start_NhanThongDiepHuy → Task_EventCapNhatHuy → Task_EventGuiThongBaoHuy → End_EventHuy.

    Event sub-process ngắt (interrupting): dừng mọi nhiệm vụ và timer đang chạy của yêu cầu.
    """
    req = get_req(db, rid)
    if req["status"] not in CANCELLABLE:
        raise ProcessError(
            f'Không thể hủy yêu cầu ở trạng thái "{STATUS[req["status"]]["label"]}". '
            "Chỉ hủy được trước khi bảng điểm được ký số.")
    reason = norm_space(reason) or "Sinh viên không còn nhu cầu"
    interrupted = STATUS[req["status"]]["step"]
    req["timers"] = {}
    trace(db, req, "Start_NhanThongDiepHuy", actor, f"Nhận thông điệp hủy: {reason}", "message-start")
    trace(db, req, "Task_EventCapNhatHuy", "Hệ thống", f"Ngắt bước \"{STEPS[interrupted][0]}\", hủy hồ sơ và ghi nhật ký")
    sys_log(db, "warn", f"Sinh viên chủ động hủy yêu cầu {req['id']}: {reason}", req["id"], actor)
    send_email(
        db, req, "Task_EventGuiThongBaoHuy", req["form"]["email"], "SV", f"[{req['id']}] Xác nhận đã hủy yêu cầu cấp bảng điểm",
        f"Chào bạn,\n\nHệ thống đã hủy yêu cầu {req['id']} theo đề nghị của bạn.\nLý do: {reason}\n\n"
        "Bạn có thể tạo yêu cầu mới bất cứ lúc nào.\n\nPhòng Đào tạo",
    )
    trace(db, req, "Task_EventGuiThongBaoHuy", "Hệ thống", "Đã gửi email xác nhận hủy")
    req["decisionNote"] = reason
    set_status(db, req, "SV_HUY")
    trace(db, req, "End_EventHuy", "Hệ thống", "Yêu cầu đã hủy (SV chủ động)")
    return req


# ---------------------------- Sự kiện thời gian ----------------------------
def tick(db: Db) -> list[dict]:
    """Quét timer biên: e_t3 (ngắt), b_khoa và b_pp (không ngắt, nhắc 1 lần)."""
    t = now(db)
    fired = []
    cfg = db.config
    for req in db.requests:
        tm = req["timers"]
        if req["status"] == "CHO_BO_SUNG" and tm.get("supplementDue") and t >= tm["supplementDue"]:
            tm.pop("supplementDue", None)
            trace(db, req, "e_t3", "Hệ thống", f"Quá {cfg['supplementDays']} ngày không bổ sung", "timer")
            trace(db, req, "t_huy", "Hệ thống", "Hủy yêu cầu và lưu log")
            sys_log(db, "warn", f"Hủy yêu cầu {req['id']} do quá hạn bổ sung", req["id"])
            send_email(
                db, req, "t_guihuy", req["form"]["email"], "SV", f"[{req['id']}] Yêu cầu cấp bảng điểm đã bị hủy",
                f"Chào bạn,\n\nYêu cầu {req['id']} đã bị hủy do quá {cfg['supplementDays']} ngày không bổ sung thông tin.\n"
                "Bạn có thể tạo yêu cầu mới bất cứ lúc nào.\n\nPhòng Đào tạo",
            )
            trace(db, req, "t_guihuy", "Hệ thống", "Đã gửi email thông báo hủy")
            trace(db, req, "s_nhan_huy", req["form"]["hoTen"], "Sinh viên nhận thông báo hủy")
            set_status(db, req, "DA_HUY")
            trace(db, req, "s_end_huy", "Hệ thống", "Yêu cầu đã hủy (quá hạn bổ sung)")
            fired.append({"reqId": req["id"], "timer": "e_t3"})
        if req["status"] == "CHO_KHOA" and not tm.get("khoaReminded") and tm.get("khoaRemindAt") and t >= tm["khoaRemindAt"]:
            tm["khoaReminded"] = True
            st = find_student(db, req["form"]["mssv"]) or {}
            trace(db, req, "b_khoa", "Hệ thống", f"Khoa chưa xử lý sau {cfg['khoaRemindDays']} ngày", "timer")
            send_email(
                db, req, "t_nhackhoa", dept_mailbox(db, st.get("khoa")), "KHOA",
                f"[Nhắc việc] {req['id']} chờ Khoa rà soát điểm quá {cfg['khoaRemindDays']} ngày",
                f"Kính gửi {st.get('khoa') or 'Khoa'},\n\nYêu cầu {req['id']} của SV {req['form']['mssv']} đang chờ rà soát & hiệu chỉnh điểm.\n"
                "Vui lòng xử lý sớm.\n\nHệ thống cấp phát bảng điểm",
            )
            trace(db, req, "t_nhackhoa", "Hệ thống", "Đã gửi email nhắc Khoa")
            trace(db, req, "end_nhackhoa", "Hệ thống", "Đã nhắc Khoa")
            fired.append({"reqId": req["id"], "timer": "b_khoa"})
        if req["status"] == "CHO_PHE_DUYET" and not tm.get("ppReminded") and tm.get("ppRemindAt") and t >= tm["ppRemindAt"]:
            tm["ppReminded"] = True
            trace(db, req, "b_pp", "Hệ thống", f"Phó phòng chưa duyệt sau {cfg['ppRemindDays']} ngày", "timer")
            send_email(
                db, req, "t_nhacpp", f"phophong.daotao@{cfg['emailDomain']}", "PP",
                f"[Nhắc việc] {req['id']} chờ phê duyệt quá {cfg['ppRemindDays']} ngày",
                f"Kính gửi Phó phòng,\n\nBảng điểm của yêu cầu {req['id']} (SV {req['form']['mssv']}) đang chờ xem xét.\n\n"
                "Hệ thống cấp phát bảng điểm",
            )
            trace(db, req, "t_nhacpp", "Hệ thống", "Đã gửi email nhắc Phó phòng")
            trace(db, req, "Event_1j9h9e1", "Hệ thống", "Đã nhắc Phó phòng")
            fired.append({"reqId": req["id"], "timer": "b_pp"})
    return fired


# ----------------------------- Tra cứu, thống kê -----------------------------
def verify(db: Db, code: str) -> dict:
    c = re.sub(r"[^0-9A-F]", "", str(code or "").strip().upper())
    if len(c) < 12:
        return {"found": False}
    entry = next((a for a in db.archive if a["code"].replace("-", "") == c[:12]), None)
    if not entry:
        return {"found": False}
    h = transcript_hash(entry["transcript"])
    sig_ok = db.signer is not None and db.signer.verify(entry["hash"], entry["signature"])
    return {"found": True, "valid": h == entry["hash"] and sig_ok, "hashOk": h == entry["hash"], "signatureOk": sig_ok,
            "entry": entry}


def stats(db: Db) -> dict:
    by_status = {k: 0 for k in STATUS}
    for r in db.requests:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    done = db.issuance
    avg = jround(sum(x["leadTimeH"] for x in done) / len(done), 1) if done else None
    auto = sum(1 for r in db.requests if any(h["step"] == "g_diem" and h["note"].startswith("Có") for h in r["history"]))
    return {"total": len(db.requests), "byStatus": by_status, "issued": len(done), "avgLeadH": avg, "autoPass": auto}


def deadline_of(req: dict) -> dict | None:
    t = req.get("timers") or {}
    if req["status"] == "CHO_BO_SUNG" and t.get("supplementDue"):
        return {"at": t["supplementDue"], "label": "Tự hủy"}
    if req["status"] == "CHO_KHOA" and t.get("khoaRemindAt") and not t.get("khoaReminded"):
        return {"at": t["khoaRemindAt"], "label": "Nhắc Khoa"}
    if req["status"] == "CHO_PHE_DUYET" and t.get("ppRemindAt") and not t.get("ppReminded"):
        return {"at": t["ppRemindAt"], "label": "Nhắc Phó phòng"}
    return None
