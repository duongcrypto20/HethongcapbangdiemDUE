"""Kiểm thử API: xác thực, phân quyền theo làn BPMN, CSRF, lưu trữ bền vững và tra cứu chữ ký.

Chạy:  python -m unittest discover -s tests -v
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bd-api-")
        self.cfg = {"DATA_DIR": self.tmp, "KEY_DIR": self.tmp + "/keys", "DB_PATH": self.tmp + "/test.db",
                    "DEMO_PASSWORD": "123456", "TESTING": True}
        self.app = create_app(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, username, password="123456"):
        c = self.app.test_client()
        r = c.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(r.status_code, 200, r.get_json())
        c.csrf = r.get_json()["csrf"]
        return c

    def post(self, c, url, data=None):
        return c.post(url, json=data or {}, headers={"X-CSRF-Token": c.csrf})

    def test_dang_nhap_sai_mat_khau(self):
        c = self.app.test_client()
        self.assertEqual(c.post("/api/login", json={"username": "pdt.hong", "password": "sai"}).status_code, 401)
        self.assertEqual(c.get("/api/state").status_code, 401)

    def test_khoa_tai_khoan_sau_5_lan_sai(self):
        c = self.app.test_client()
        for _ in range(5):
            c.post("/api/login", json={"username": "pp.lethi", "password": "sai"})
        self.assertEqual(c.post("/api/login", json={"username": "pp.lethi", "password": "123456"}).status_code, 429)

    def test_phan_quyen_theo_lan(self):
        sv = self.login("221121521101")
        # SV không được làm việc của Phòng Đào tạo / Phó phòng
        reqs = self.app.test_client()
        pdt = self.login("pdt.hong")
        waiting = [r for r in pdt.get("/api/state").get_json()["requests"] if r["status"] == "CHO_KIEM_TRA"]
        rid = waiting[0]["id"]
        self.assertEqual(self.post(sv, f"/api/requests/{rid}/qc", {"ok": True}).status_code, 403)
        # SV chỉ thấy yêu cầu của mình
        mine = sv.get("/api/state").get_json()["requests"]
        self.assertTrue(all(r["form"]["mssv"] == "221121521101" for r in mine))
        self.assertEqual(sv.get(f"/api/requests/{rid}").status_code, 403)
        # Khoa chỉ thấy SV thuộc Khoa mình
        khoa = self.login("khoa.thongketinhoc")
        depts = {r["dept"] for r in khoa.get("/api/state").get_json()["requests"]}
        self.assertEqual(depts, {"Khoa Thống kê – Tin học"})
        del reqs

    def test_csrf_bat_buoc(self):
        sv = self.login("221121521101")
        r = sv.post("/api/requests", json={"mucDich": "Nộp hồ sơ học bổng"})
        self.assertEqual(r.status_code, 403)

    def test_luong_day_du_qua_api_va_luu_ben_vung(self):
        sv = self.login("221121506109")
        r = self.post(sv, "/api/requests", {"hoTen": "Trương Mỹ Duyên", "ngaySinh": "2004-12-03", "email": "221121506109@due.udn.vn",
                                            "sdt": "0912345678", "mucDich": "Hồ sơ xin việc", "ngonNgu": "vi"})
        self.assertEqual(r.status_code, 200, r.get_json())
        rid = r.get_json()["request"]["id"]
        self.assertEqual(r.get_json()["request"]["status"], "CHO_KIEM_TRA")
        pdt = self.login("pdt.hong")
        self.assertEqual(self.post(pdt, f"/api/requests/{rid}/qc", {"ok": False}).status_code, 400)  # thiếu góp ý
        self.assertEqual(self.post(pdt, f"/api/requests/{rid}/qc", {"ok": True}).status_code, 200)
        self.assertEqual(self.post(pdt, f"/api/requests/{rid}/qc", {"ok": True}).status_code, 409)  # sai bước
        pp = self.login("pp.lethi")
        r = self.post(pp, f"/api/requests/{rid}/pp-decision", {"decision": "approve"})
        self.assertEqual(r.get_json()["request"]["status"], "HOAN_TAT")
        code = r.get_json()["request"]["signature"]["code"]
        # Khởi động lại ứng dụng: dữ liệu vẫn còn (SQLite) và chữ ký vẫn kiểm chứng được (cùng khóa)
        app2 = create_app(self.cfg)
        v = app2.test_client().get(f"/api/verify/{code}").get_json()
        self.assertTrue(v["found"] and v["valid"], v)
        self.assertIn("BEGIN PUBLIC KEY", app2.test_client().get("/api/public-key").get_data(as_text=True))

    def test_sv_chu_dong_huy_qua_api(self):
        sv = self.login("221121502106")
        rid = next(r["id"] for r in sv.get("/api/state").get_json()["requests"] if r["status"] == "CHO_KHOA")
        r = self.post(sv, f"/api/requests/{rid}/cancel", {"reason": "Không cần nữa"})
        self.assertEqual(r.get_json()["request"]["status"], "SV_HUY")

    def test_gia_lap_su_co_truy_xuat(self):
        pdt = self.login("pdt.hong")
        self.post(pdt, "/api/admin/fault", {"on": True})
        sv = self.login("221121521101")
        r = self.post(sv, "/api/requests", {"hoTen": "Trần Minh Anh", "ngaySinh": "2004-03-12", "email": "221121521101@due.udn.vn",
                                            "sdt": "0912345678", "mucDich": "Nộp hồ sơ học bổng"})
        self.assertEqual(r.get_json()["request"]["status"], "LOI_HE_THONG")

    def test_nhap_csv_tao_tai_khoan(self):
        pdt = self.login("pdt.hong")
        csv = "MSSV;Họ và tên;Ngày sinh;Khoa;Email\n231121521199;Lý Thị Mới;01/02/2005;Khoa Thống kê – Tin học;231121521199@due.udn.vn\n"
        r = self.post(pdt, "/api/admin/import/students", {"text": csv})
        self.assertEqual(r.get_json()["result"]["added"], 1)
        self.login("231121521199")  # tài khoản SSO được tạo tự động

    def test_tua_dong_ho_kich_hoat_timer(self):
        pdt = self.login("pdt.hong")
        r = self.post(pdt, "/api/admin/clock", {"ms": 3 * 86_400_000})
        self.assertTrue(any(f["timer"] == "e_t3" for f in r.get_json()["fired"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
