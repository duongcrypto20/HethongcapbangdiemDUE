"""Đọc dữ liệu test (CSV hoặc JSON) của giảng viên; chấp nhận tiêu đề tiếng Việt có dấu."""
from __future__ import annotations

import csv
import io
import json
import re

from .engine import ProcessError, strip_diacritics

ALIAS = {
    "ma_sv": "mssv", "ma_so_sinh_vien": "mssv", "ma_sinh_vien": "mssv", "ho_va_ten": "ho_ten", "hoten": "ho_ten",
    "ngaysinh": "ngay_sinh", "diem": "diem_10", "diem10": "diem_10", "diem_he_10": "diem_10", "diem_so": "diem_10",
    "diem_tk": "diem_10", "diemchu": "diem_chu", "tin_chi": "so_tc", "so_tin_chi": "so_tc", "sotc": "so_tc",
    "ma_hoc_phan": "ma_hp", "mahp": "ma_hp", "ten_hoc_phan": "ten_hp", "tenhp": "ten_hp", "hk": "hoc_ky",
    "hoc_ki": "hoc_ky", "hocky": "hoc_ky", "namhoc": "nam_hoc", "so_dien_thoai": "sdt", "dien_thoai": "sdt",
    "muc_dich_su_dung": "muc_dich", "so_ban_giay": "so_ban", "khoa_quan_ly": "khoa", "nien_khoa": "khoa_hoc",
}


def key_of(h: str) -> str:
    k = re.sub(r"[^a-z0-9]+", "_", strip_diacritics(h).lower().strip()).strip("_")
    return ALIAS.get(k, k)


def parse_any(text: str, kind: str | None = None) -> list[dict]:
    t = (text or "").lstrip("﻿").strip()
    if not t:
        raise ProcessError("Chưa có dữ liệu. Dán nội dung CSV/JSON hoặc chọn tệp.", 400)
    if t[0] in "[{":
        try:
            data = json.loads(t)
        except json.JSONDecodeError as exc:
            raise ProcessError(f"JSON không hợp lệ: {exc}", 400) from exc
        if isinstance(data, dict):
            data = data.get(kind or "", []) if kind else []
        if not isinstance(data, list):
            raise ProcessError("JSON phải là một mảng các bản ghi", 400)
        return [d for d in data if isinstance(d, dict)]
    first = t.splitlines()[0]
    delim = "\t" if "\t" in first else (";" if first.count(";") > first.count(",") else ",")
    rows = [r for r in csv.reader(io.StringIO(t), delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        return []
    head = [key_of(h) for h in rows[0]]
    return [{h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(head)} for r in rows[1:]]


def to_csv(rows: list[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
    return "﻿" + buf.getvalue()
