"""Kiểm thử API: xác thực, phân quyền theo làn BPMN, CSRF, lưu trữ bền vững và tra cứu chữ ký.

Chạy:  python -m unittest discover -s tests -v
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bd-api-")
        self.cfg = {"DATA_DIR": self.tmp, "KEY_DIR": self.tmp + "/keys", "DB_PATH": self.tmp + "/test.db",
                    "DEMO_MODE": False, "DEMO_PASSWORD": "123456", "TESTING": True}
        self.app = create_app(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, username, password=None):
        if password is None:
            password = username if self.cfg["DEMO_MODE"] and username.isdigit() else self.cfg["DEMO_PASSWORD"]
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

    def test_login_returns_user_without_second_database_lookup(self):
        c = self.app.test_client()
        with patch("bangdiem.store.get_user", side_effect=AssertionError("unexpected follow-up lookup")):
            response = c.post("/api/login", json={"username": "pdt.hong", "password": "123456"})

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["user"]["username"], "pdt.hong")
        self.assertTrue(response.get_json()["csrf"])

    def test_sinh_vien_dang_nhap_bang_ho_ten_va_mssv(self):
        demo_app = create_app({**self.cfg, "DEMO_MODE": True, "DEMO_PASSWORD": "ignored-in-demo-mode"})
        c = demo_app.test_client()
        username = "  trần minh anh "
        mssv = "221121521101"
        demo = c.get("/api/me").get_json()["demo"]
        self.assertEqual(demo["password"], "123456")
        student_account = next(a for a in demo["accounts"] if a["mssv"] == mssv)
        self.assertEqual(student_account["username"], "Trần Minh Anh")
        r = c.post("/api/login", json={"username": username, "password": mssv})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(c.post("/api/logout").status_code, 200)
        student_id_login = c.post("/api/login", json={"username": mssv, "password": mssv})
        self.assertEqual(student_id_login.status_code, 200, student_id_login.get_json())
        self.assertEqual(c.post("/api/logout").status_code, 200)
        wrong_password = c.post("/api/login", json={"username": username, "password": "123456"})
        self.assertEqual(wrong_password.status_code, 401)
        staff_login = c.post("/api/login", json={"username": "pdt.hong", "password": "123456"})
        self.assertEqual(staff_login.status_code, 200, staff_login.get_json())
        self.assertEqual(c.post("/api/logout").status_code, 200)
        department_login = c.post("/api/login", json={"username": "khoa.thongketinhoc", "password": "123456"})
        self.assertEqual(department_login.status_code, 200, department_login.get_json())

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

    def test_khoa_detail_shows_read_only_assistance_not_other_roles(self):
        khoa = self.login("khoa.thongketinhoc")
        pending = next(
            r for r in khoa.get("/api/state").get_json()["requests"]
            if r["status"] == "CHO_KHOA"
        )
        response = khoa.get(f"/api/requests/{pending['id']}")

        self.assertEqual(response.status_code, 200, response.get_json())
        assistant = response.get_json()["reviewAssistant"]
        self.assertEqual(assistant["method"], "local-rules-and-source-comparison")
        self.assertTrue(assistant["readOnly"])
        self.assertTrue(assistant["humanDecisionRequired"])
        self.assertTrue(assistant["sourceComparisons"])
        self.assertEqual(assistant["sourceComparisons"][0]["sourceKind"], "demo")
        self.assertGreater(assistant["sourceComparisons"][0]["differenceCount"], 0)
        self.assertIn("không tự sửa dữ liệu", assistant["limitations"])
        self.assertIn("BẢN NHÁP", assistant["draftNote"])

        pdt = self.login("pdt.hong")
        pdt_detail = pdt.get(f"/api/requests/{pending['id']}").get_json()
        self.assertNotIn("reviewAssistant", pdt_detail)

    def test_pdt_can_replace_reference_source_without_changing_live_grades(self):
        pdt = self.login("pdt.hong")
        before = pdt.get("/api/admin/grades?mssv=221121521103").get_json()
        source_csv = (
            "mssv,nam_hoc,hoc_ky,ma_hp,ten_hp,so_tc,diem_10,diem_chu\n"
            "221121521103,2022-2023,HK1,MIS1001,Tin học văn phòng,3,8.0,B\n"
        )
        imported = self.post(pdt, "/api/admin/reference-grades", {
            "sourceName": "Nguồn tham chiếu kiểm thử",
            "text": source_csv,
        })
        self.assertEqual(imported.status_code, 200, imported.get_json())
        self.assertEqual(imported.get_json()["result"]["added"], 1)

        after = pdt.get("/api/admin/grades?mssv=221121521103").get_json()
        self.assertEqual(before["grades"], after["grades"])
        self.assertEqual(after["referenceSources"][0]["label"], "Nguồn tham chiếu kiểm thử")
        self.assertEqual(after["referenceSources"][0]["rowCount"], 1)

        invalid = self.post(pdt, "/api/admin/reference-grades", {
            "sourceName": "Nguồn sai",
            "text": "mssv,diem_10\n123,8\n",
        })
        self.assertEqual(invalid.status_code, 400, invalid.get_json())
        still_present = pdt.get("/api/admin/grades").get_json()["referenceSources"]
        self.assertEqual(still_present[0]["label"], "Nguồn tham chiếu kiểm thử")

        sv = self.login("221121521101")
        forbidden = self.post(sv, "/api/admin/reference-grades", {"text": source_csv})
        self.assertEqual(forbidden.status_code, 403)

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
