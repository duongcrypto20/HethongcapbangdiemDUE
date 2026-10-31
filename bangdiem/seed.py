"""Dữ liệu mẫu (hư cấu): CSDL sinh viên, CSDL điểm và vài yêu cầu ở các trạng thái khác nhau.

Mỗi sinh viên mẫu được thiết kế để đi qua một nhánh khác nhau của BPMN to-be.
"""
from __future__ import annotations

import time

from . import engine as E

COMMON = [
    [("TRI1001", "Triết học Mác – Lênin", 3), ("MAT1001", "Toán ứng dụng trong kinh tế", 3), ("ECO1001", "Kinh tế vi mô", 3),
     ("ENG1001", "Tiếng Anh cơ sở 1", 3), ("MIS1001", "Tin học văn phòng", 3)],
    [("TRI1002", "Kinh tế chính trị Mác – Lênin", 2), ("ECO1002", "Kinh tế vĩ mô", 3), ("STA2001", "Nguyên lý thống kê", 3),
     ("MGT1001", "Quản trị học", 3), ("LAW1001", "Pháp luật đại cương", 2)],
]
MAJOR = {
    "Hệ thống thông tin quản lý": [
        [("MIS2001", "Cơ sở dữ liệu", 3), ("MIS2002", "Lập trình căn bản", 3), ("MIS2003", "Hệ thống thông tin quản lý", 3),
         ("ACC2001", "Nguyên lý kế toán", 3), ("STA2002", "Thống kê kinh doanh", 3)],
        [("MIS3001", "Phân tích và thiết kế hệ thống", 3), ("MIS3002", "Mạng máy tính", 3), ("MIS3003", "Lập trình web", 3),
         ("MIS3047", "Quản lý quy trình kinh doanh", 3), ("FIN2001", "Tài chính doanh nghiệp", 3)],
    ],
    "Quản trị kinh doanh": [
        [("MKT2001", "Marketing căn bản", 3), ("MGT2001", "Quản trị nguồn nhân lực", 3), ("ACC2001", "Nguyên lý kế toán", 3),
         ("MGT2002", "Hành vi tổ chức", 3), ("STA2002", "Thống kê kinh doanh", 3)],
        [("MGT3001", "Quản trị chiến lược", 3), ("MGT3002", "Quản trị vận hành", 3), ("MGT3003", "Quản trị dự án", 3),
         ("FIN2001", "Tài chính doanh nghiệp", 3), ("MIS3047", "Quản lý quy trình kinh doanh", 3)],
    ],
    "Kế toán": [
        [("ACC2001", "Nguyên lý kế toán", 3), ("ACC2002", "Kế toán tài chính 1", 3), ("FIN2001", "Tài chính doanh nghiệp", 3),
         ("LAW2001", "Luật kinh tế", 2), ("STA2002", "Thống kê kinh doanh", 3)],
        [("ACC3001", "Kế toán tài chính 2", 3), ("ACC3002", "Kế toán quản trị", 3), ("ACC3003", "Kiểm toán căn bản", 3),
         ("TAX3001", "Thuế", 3), ("MIS3004", "Hệ thống thông tin kế toán", 3)],
    ],
}
DEPT = {
    "Hệ thống thông tin quản lý": "Khoa Thống kê – Tin học",
    "Quản trị kinh doanh": "Khoa Quản trị kinh doanh",
    "Kế toán": "Khoa Kế toán",
}
LOP = {"Hệ thống thông tin quản lý": "K21", "Quản trị kinh doanh": "K02", "Kế toán": "K06"}

# mssv, họ tên, ngày sinh, giới tính, ngành, năm nhập học, trạng thái, điểm TB kỳ vọng, số học kỳ, kịch bản
STUDENTS = [
    ("221121521101", "Trần Minh Anh", "2004-03-12", "Nữ", "Hệ thống thông tin quản lý", 2022, "Đang học", 8.1, 4, "Dữ liệu sạch — luồng chính, chỉ bản điện tử"),
    ("221121502102", "Lê Hoàng Bảo", "2004-07-25", "Nam", "Quản trị kinh doanh", 2022, "Đang học", 7.0, 4, "Có học lại 1 môn — đang chờ Phó phòng duyệt"),
    ("221121521103", "Phạm Gia Hân", "2004-01-08", "Nữ", "Hệ thống thông tin quản lý", 2022, "Đang học", 7.6, 4, "Thiếu điểm 1 học phần — chuyển Khoa"),
    ("221121506104", "Võ Đức Khang", "2004-11-30", "Nam", "Kế toán", 2022, "Đang học", 7.4, 4, "Điểm chữ sai so với điểm số; khai sai ngày sinh"),
    ("221121502105", "Đặng Ngọc Linh", "2004-05-17", "Nữ", "Quản trị kinh doanh", 2022, "Đang học", 7.9, 4, "Học phần bị nhập trùng trong cùng học kỳ"),
    ("221121502106", "Huỳnh Quốc Nam", "2004-09-02", "Nam", "Quản trị kinh doanh", 2022, "Đang học", 8.6, 4, "Điểm bất thường — Khoa cần xác nhận"),
    ("201121521107", "Bùi Thu Phương", "2002-02-14", "Nữ", "Hệ thống thông tin quản lý", 2020, "Đã tốt nghiệp", 8.4, 4, "Đã tốt nghiệp — nhận cả bản giấy"),
    ("241121506108", "Ngô Tuấn Kiệt", "2006-06-21", "Nam", "Kế toán", 2024, "Đang học", 7.0, 0, "Chưa có dữ liệu điểm — Khoa từ chối"),
    ("221121506109", "Trương Mỹ Duyên", "2004-12-03", "Nữ", "Kế toán", 2022, "Đang học", 7.7, 4, "Dữ liệu sạch — chờ PĐT kiểm tra"),
    ("221121521110", "Phan Thành Đạt", "2004-04-19", "Nam", "Hệ thống thông tin quản lý", 2022, "Đang học", 7.2, 4, "Không bổ sung thông tin — bị hủy sau 3 ngày"),
]

M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return (a * b) & M32


def rng(seed: int):
    """Bộ sinh số giả ngẫu nhiên mulberry32 (cho dữ liệu mẫu cố định, lặp lại được)."""
    state = [seed & M32]

    def r() -> float:
        state[0] = (state[0] + 0x6D2B79F5) & M32
        s = state[0]
        t = _imul(s ^ (s >> 15), 1 | s)
        t = (((t + _imul(t ^ (t >> 7), 61 | t)) & M32) ^ t) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296

    return r


def build_data() -> dict:
    students, grades, scenarios = [], [], {}
    for idx, (mssv, ho_ten, ngay_sinh, gioi_tinh, nganh, start, trang_thai, mu, n_terms, scenario) in enumerate(STUDENTS):
        k = start - 1974  # 2022 → K48
        students.append({
            "mssv": mssv, "hoTen": ho_ten, "ngaySinh": ngay_sinh, "gioiTinh": gioi_tinh, "nganh": nganh, "khoa": DEPT[nganh],
            "lop": f"{k}{LOP[nganh]}.{idx % 2 + 1}", "khoaHoc": f"K{k}", "email": f"{mssv}@due.udn.vn", "trangThai": trang_thai,
        })
        scenarios[mssv] = scenario
        rand = rng(int(mssv[-4:]) * 7919)
        plan = (COMMON + MAJOR[nganh])[:n_terms]
        for i, courses in enumerate(plan):
            year = start + i // 2
            for ma, ten, tc in courses:
                d = E.jround(min(10, max(4.2, mu + (rand() - 0.5) * 2.4)), 1)
                grades.append({"mssv": mssv, "namHoc": f"{year}-{year + 1}", "hocKy": f"HK{i % 2 + 1}", "maHP": ma, "tenHP": ten,
                               "soTC": tc, "diem10": d, "diemChu": E.letter_of(d)["letter"]})

    def find(mssv: str, ma: str) -> dict:
        return next(g for g in grades if g["mssv"] == mssv and g["maHP"] == ma)

    # Bảo: rớt ECO1002 ở HK2 năm 1, học lại đạt ở HK1 năm 2
    find("221121502102", "ECO1002").update(diem10=3.8, diemChu="F")
    grades.append({"mssv": "221121502102", "namHoc": "2023-2024", "hocKy": "HK1", "maHP": "ECO1002", "tenHP": "Kinh tế vĩ mô",
                   "soTC": 3, "diem10": 6.6, "diemChu": "C+"})
    # Hân: thiếu điểm Lập trình web
    find("221121521103", "MIS3003").update(diem10=None, diemChu="")
    # Khang: điểm chữ sai
    find("221121506104", "ACC2002").update(diem10=7.2, diemChu="A")
    # Linh: nhập trùng Marketing căn bản
    grades.append({**find("221121502105", "MKT2001"), "diem10": 6.0, "diemChu": "C"})
    # Nam: một điểm lệch rất xa điểm TB
    find("221121502106", "MGT3002").update(diem10=3.0, diemChu="F")
    return {"students": students, "grades": grades, "scenarios": scenarios}


def form_of(st: dict, **extra) -> dict:
    f = {"mssv": st["mssv"], "hoTen": st["hoTen"], "ngaySinh": st["ngaySinh"], "email": st["email"],
         "sdt": "09" + st["mssv"][-8:], "mucDich": "Nộp hồ sơ xin học bổng", "ngonNgu": "vi", "banGiay": False, "soBan": 0,
         "ghiChu": ""}
    f.update(extra)
    return f


def load_reference_data(db: E.Db) -> None:
    data = build_data()
    E.import_students(db, data["students"], "replace")
    E.import_grades(db, data["grades"], "replace")
    db.logs = []


def populate_sample(db: E.Db, base: int | None = None) -> E.Db:
    """Nạp dữ liệu mẫu và chạy sẵn vài yêu cầu trong mấy ngày trước để mở ra đã có việc."""
    load_reference_data(db)
    real = base if base is not None else int(time.time() * 1000)

    def at(h: float) -> None:
        db.fixed_now = int(real + h * E.HOUR)

    def st(m: str) -> dict:
        return E.find_student(db, m)

    PDT, PP = "CV. Nguyễn Thị Hồng (PĐT)", "ThS. Lê Thị Phó Phòng"
    # 1. Minh Anh — hoàn tất, chỉ bản điện tử
    at(-100); r = E.submit_request(db, form_of(st("221121521101"), mucDich="Nộp hồ sơ thực tập tại doanh nghiệp"))
    at(-98); E.qc_decide(db, r["id"], True, "", PDT)
    at(-80); E.pp_decide(db, r["id"], "approve", "", PP)
    # 10. Đạt — số điện thoại sai, không bổ sung → bị hủy khi quét timer
    at(-90); E.submit_request(db, form_of(st("221121521110"), sdt="09123", mucDich="Xin việc làm thêm"))
    # 7. Phương — tốt nghiệp, có bản giấy, hoàn tất
    at(-75); r = E.submit_request(db, form_of(st("201121521107"), mucDich="Hồ sơ du học thạc sĩ", ngonNgu="en", banGiay=True, soBan=3))
    at(-73); E.qc_decide(db, r["id"], False, "Bổ sung ghi chú tình trạng đã tốt nghiệp trên bảng điểm", PDT)
    at(-72); E.edit_transcript(db, r["id"], {"ghiChuBangDiem": "Sinh viên đã tốt nghiệp năm 2024."}, PDT)
    at(-71); E.qc_decide(db, r["id"], True, "", PDT)
    at(-60); E.pp_decide(db, r["id"], "approve", "", PP)
    at(-58); E.print_paper(db, r["id"], PDT)
    at(-55); E.stamp_paper(db, r["id"], PP)
    at(-50); E.confirm_paper(db, r["id"], "Bùi Thu Phương", PDT)
    # 3. Hân — thiếu điểm → chờ Khoa quá 2 ngày (sẽ được nhắc)
    at(-54); E.submit_request(db, form_of(st("221121521103"), mucDich="Đăng ký chương trình trao đổi sinh viên"))
    # 4. Khang — khai sai ngày sinh → chờ bổ sung
    at(-26); E.submit_request(db, form_of(st("221121506104"), ngaySinh="2004-11-03", mucDich="Nộp hồ sơ học bổng doanh nghiệp"))
    # 2. Bảo — đã qua kiểm tra, chờ Phó phòng
    at(-22); r = E.submit_request(db, form_of(st("221121502102"), mucDich="Bổ sung hồ sơ thực tập", banGiay=True, soBan=2))
    at(-20); E.qc_decide(db, r["id"], True, "", PDT)
    # 6. Nam — điểm bất thường → chờ Khoa
    at(-3); E.submit_request(db, form_of(st("221121502106"), mucDich="Xét học bổng khuyến khích học tập"))
    # 9. Duyên — chờ PĐT kiểm tra
    at(-1); E.submit_request(db, form_of(st("221121506109"), mucDich="Hồ sơ xin việc", ngonNgu="en"))
    db.fixed_now = None
    E.tick(db)  # kích hoạt các timer đã đến hạn (hủy yêu cầu của Đạt, nhắc Khoa)
    return db
