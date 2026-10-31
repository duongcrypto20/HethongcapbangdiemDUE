"""Sinh tệp CSV mẫu trong data/ (cùng định dạng dữ liệu test của giảng viên).

Chạy:  python tools/xuat_du_lieu_mau.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bangdiem import seed  # noqa: E402
from bangdiem.csvio import to_csv  # noqa: E402

d = seed.build_data()
out = ROOT / "data"
out.mkdir(exist_ok=True)
dmy = lambda iso: "/".join(reversed(iso.split("-")))  # noqa: E731
(out / "mau-sinh-vien.csv").write_text(to_csv(
    [{"mssv": s["mssv"], "ho_ten": s["hoTen"], "ngay_sinh": dmy(s["ngaySinh"]), "gioi_tinh": s["gioiTinh"], "lop": s["lop"],
      "khoa": s["khoa"], "nganh": s["nganh"], "khoa_hoc": s["khoaHoc"], "email": s["email"], "trang_thai": s["trangThai"]}
     for s in d["students"]],
    ["mssv", "ho_ten", "ngay_sinh", "gioi_tinh", "lop", "khoa", "nganh", "khoa_hoc", "email", "trang_thai"]), encoding="utf-8")
(out / "mau-diem.csv").write_text(to_csv(
    [{"mssv": g["mssv"], "nam_hoc": g["namHoc"], "hoc_ky": g["hocKy"], "ma_hp": g["maHP"], "ten_hp": g["tenHP"],
      "so_tc": g["soTC"], "diem_10": g["diem10"], "diem_chu": g["diemChu"]} for g in d["grades"]],
    ["mssv", "nam_hoc", "hoc_ky", "ma_hp", "ten_hp", "so_tc", "diem_10", "diem_chu"]), encoding="utf-8")
(out / "mau-yeu-cau.csv").write_text("﻿" + "\n".join([
    "mssv,ho_ten,ngay_sinh,email,sdt,muc_dich,ngon_ngu,ban_giay,so_ban",
    "221121521101,,,,,Nộp hồ sơ học bổng,vi,0,",
    "221121502105,,,,,Hồ sơ thực tập,vi,1,2",
    "221121506104,Võ Đức Khang,03/11/2004,,,Hồ sơ học bổng,vi,0,",
    "221121502106,,,,,Xét học bổng,en,0,",
    "241121506108,,,,,Hồ sơ chuyển trường,vi,0,",
    "221121521110,Phan Thanh Dat,,,0905xx,Xin việc,vi,0,",
    "999999999999,Người Lạ,01/01/2000,abc@gmail.com,0905123456,Thử MSSV không tồn tại,vi,0,",
]) + "\n", encoding="utf-8")
print("Đã ghi data/mau-sinh-vien.csv, data/mau-diem.csv, data/mau-yeu-cau.csv")
