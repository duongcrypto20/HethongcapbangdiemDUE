"""Kiểm thử bộ máy quy trình: mỗi kịch bản phủ một nhánh của BPMN to-be (đã sửa).

Chạy:  python -m unittest discover -s tests -v
"""
import copy
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bangdiem import engine as E  # noqa: E402
from bangdiem import seed as S  # noqa: E402
from bangdiem.signing import Signer  # noqa: E402

T0 = int(datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc).timestamp() * 1000)  # 09:00 giờ VN
_KEYDIR = tempfile.mkdtemp(prefix="bd-keys-")
SIGNER = Signer(_KEYDIR, passphrase="mat-khau-kiem-thu")
PDT, PP, KHOA = "Chuyên viên PĐT", "Phó phòng", "Khoa"


def fresh_db() -> E.Db:
    db = E.Db(fixed_now=T0)
    S.load_reference_data(db)
    db.signer = SIGNER
    return db


def form(db, mssv, **extra):
    return S.form_of(E.find_student(db, mssv), **extra)


def steps(r):
    return [h["step"] for h in r["history"]]


class LuongChinh(unittest.TestCase):
    def test_tc01_luong_chinh_hoan_tat(self):
        """TC01 s_task → ca_xt → t_truyxuat → t_doichieu → t_tao → g_dat → t_pd → t_dongdau → t_guidt → t_nhatky → end_ht"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521101"))
        self.assertEqual(r["status"], "CHO_KIEM_TRA")
        E.qc_decide(db, r["id"], True, "", PDT)
        E.pp_decide(db, r["id"], "approve", "", PP)
        self.assertEqual(r["status"], "HOAN_TAT")
        self.assertTrue(any(m["step"] == "t_guidt" and m["reqId"] == r["id"] for m in db.outbox))
        self.assertEqual(len(db.issuance), 1)
        self.assertEqual(steps(r)[-1], "end_ht")
        self.assertIn("t_nhatky", steps(r))

    def test_tc12_ban_giay_cong_bao_ham(self):
        """TC12 Gateway_0m52u6m → t_guidt ‖ t_in → Activity_0xvx345 → Activity_15aejsy → Gateway_198pqrp"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "201121521107", banGiay=True, soBan=2))
        E.qc_decide(db, r["id"], True, "", PDT)
        E.pp_decide(db, r["id"], "approve", "", PP)
        self.assertEqual(r["status"], "CHO_IN")
        self.assertEqual(len(db.issuance), 0, "Chưa ghi sổ khi bản giấy chưa xong")
        E.print_paper(db, r["id"], PDT)
        E.stamp_paper(db, r["id"], PP)
        E.confirm_paper(db, r["id"], "Bùi Thu Phương", PDT)
        self.assertEqual(r["status"], "HOAN_TAT")
        self.assertEqual(db.issuance[0]["soBanGiay"], 2)


class XacThucThongTin(unittest.TestCase):
    def test_tc02_bo_sung_thong_tin(self):
        """TC02 g_hl(Không) → Activity_0ze94gf → s_bs_task → g_m1 → ca_xt → g_hl(Có)"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121506104", ngaySinh="03/11/2004"))
        self.assertEqual(r["status"], "CHO_BO_SUNG")
        self.assertTrue(any(m["step"] == "Activity_0ze94gf" for m in db.outbox))
        E.supplement(db, r["id"], {"ngaySinh": "30/11/2004"}, "SV")
        self.assertNotEqual(r["status"], "CHO_BO_SUNG")
        self.assertEqual(r["attempts"], 2)

    def test_tc03_qua_3_ngay_tu_huy(self):
        """TC03 s_bs_task ⏱ e_t3 → t_huy → t_guihuy → s_nhan_huy → s_end_huy"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521110", sdt="12345"))
        E.advance_clock(db, 2 * E.DAY)
        self.assertEqual(r["status"], "CHO_BO_SUNG")
        E.advance_clock(db, E.DAY + 1)
        self.assertEqual(r["status"], "DA_HUY")
        self.assertTrue(any(m["step"] == "t_guihuy" for m in db.outbox))
        self.assertTrue(any(l["reqId"] == r["id"] and l["level"] == "warn" for l in db.logs))

    def test_tc13_so_khop_ho_ten(self):
        """TC13 ca_xt (luật X2): thiếu dấu được chấp nhận, sai tên bị chặn"""
        db = fresh_db()
        ok = E.validate_form(db, {**form(db, "221121521101"), "hoTen": "Tran Minh Anh"})
        bad = E.validate_form(db, {**form(db, "221121521101"), "hoTen": "Trần Minh Hùng"})
        self.assertTrue(ok["valid"], ok["nameSimilarity"])
        self.assertFalse(bad["valid"], bad["nameSimilarity"])


class NgoaiLeDuLieuDauVao(unittest.TestCase):
    def test_tc20_mssv_khong_ton_tai_chuyen_sang_bo_sung(self):
        db = fresh_db()
        r = E.submit_request(db, {
            "mssv": "000000000000", "hoTen": "Sinh viên không tồn tại",
            "ngaySinh": "2004-01-01", "email": "sv@example.com",
            "sdt": "0912345678", "mucDich": "Nộp hồ sơ học bổng",
        })

        self.assertEqual(r["status"], "CHO_BO_SUNG")
        failed_codes = {item["code"] for item in r["validation"]["items"] if not item["ok"]}
        self.assertIn("X1", failed_codes)
        self.assertIn("X4", failed_codes)
        self.assertTrue(any(mail["step"] == "Activity_0ze94gf" for mail in db.outbox))

    def test_tc21_thong_tin_ca_nhan_sai_bi_bao_loi_tuong_ung(self):
        db = fresh_db()
        st = E.find_student(db, "221121521101")
        st["trangThai"] = "Đã xóa tên"
        invalid_form = {
            **form(db, st["mssv"]), "ngaySinh": "01/01/2000",
            "email": "khong-phai-email", "sdt": "12345", "mucDich": "abc",
        }

        result = E.validate_form(db, invalid_form)
        failed_codes = {item["code"] for item in result["items"] if not item["ok"]}

        self.assertFalse(result["valid"])
        self.assertTrue({"X3", "X4", "X5", "X6", "X7"}.issubset(failed_codes))

    def test_tc22_so_ban_giay_phai_trong_gioi_han(self):
        db = fresh_db()
        base_form = {**form(db, "221121521101"), "banGiay": True}

        for copies in (1, db.config["maxCopies"]):
            with self.subTest(copies=copies):
                result = E.validate_form(db, {**base_form, "soBan": copies})
                self.assertTrue(result["valid"], result["items"])

        for copies in (0, db.config["maxCopies"] + 1, True):
            with self.subTest(copies=copies):
                result = E.validate_form(db, {**base_form, "soBan": copies})
                x8 = next(item for item in result["items"] if item["code"] == "X8")
                self.assertFalse(x8["ok"])

    def test_tc23_diem_sai_thang_diem_tin_chi_va_thieu_ma_hoc_phan(self):
        db = fresh_db()
        student_id = "221121521101"
        rows = E.grades_of(db, student_id)
        rows[0]["diem10"] = 10.1
        rows[1]["diemChu"] = "F"
        rows[2]["soTC"] = 0
        rows[3]["maHP"] = ""

        r = E.submit_request(db, form(db, student_id))
        error_codes = {error["code"] for error in r["check"]["errors"]}

        self.assertEqual(r["status"], "CHO_KHOA")
        self.assertTrue({"D2", "D3", "D4", "D7"}.issubset(error_codes))


class DoiChieuVaKhoa(unittest.TestCase):
    def test_grade_review_assistance_gives_read_only_rule_based_guidance(self):
        check = {
            "errors": [{"code": "D3", "gradeId": "g1", "msg": "Điểm chữ không khớp điểm số"}],
            "warnings": [{"code": "A1", "gradeId": "g2", "msg": "Điểm lệch so với trung bình"}],
            "infos": [{"code": "I1", "msg": "Học phần được học lại"}],
        }
        original = copy.deepcopy(check)

        result = E.grade_review_assistance(check)

        self.assertEqual(check, original)
        self.assertEqual(result["method"], "local-rules-and-source-comparison")
        self.assertTrue(result["readOnly"])
        self.assertTrue(result["humanDecisionRequired"])
        self.assertEqual([item["severity"] for item in result["findings"]], ["error", "warning", "info"])
        self.assertIn("không chứng minh điểm sai", result["findings"][1]["suggestion"])
        self.assertIn("không tự sửa dữ liệu", result["limitations"])

    def test_grade_review_compares_reference_scores_and_drafts_hypotheses(self):
        current = [{
            "id": "g1", "mssv": "123", "namHoc": "2025-2026", "hocKy": "HK1", "maHP": "MIS1001",
            "tenHP": "Tin học", "soTC": 3, "diem10": 4.0, "diemChu": "D",
        }]
        references = [{
            "sourceId": "official", "mssv": "123", "namHoc": "2025-2026", "hocKy": "HK1", "maHP": "MIS1001",
            "tenHP": "Tin học", "soTC": 3, "diem10": 8.0, "diemChu": "B",
        }]
        current_before, references_before = copy.deepcopy(current), copy.deepcopy(references)

        result = E.grade_review_assistance(
            {"errors": [], "warnings": [], "infos": []},
            current,
            [{"id": "official", "label": "Nguồn chính thức", "kind": "imported"}],
            references,
        )

        comparison = result["sourceComparisons"][0]
        self.assertEqual(comparison["differenceCount"], 1)
        self.assertEqual(comparison["differences"][0]["kind"], "mismatch")
        self.assertEqual(
            {item["field"] for item in comparison["differences"][0]["differences"]},
            {"diem10", "diemChu"},
        )
        self.assertTrue(comparison["differences"][0]["likelyCauses"])
        self.assertIn("BẢN NHÁP", result["draftNote"])
        self.assertIn("chưa phải kết luận", result["draftNote"])
        self.assertTrue(result["readOnly"])
        self.assertEqual(current, current_before)
        self.assertEqual(references, references_before)

    def test_grade_review_reports_missing_and_unreferenced_rows(self):
        current = [{
            "mssv": "123", "namHoc": "2025-2026", "hocKy": "HK1", "maHP": "LOCAL",
            "diem10": 7, "diemChu": "B", "soTC": 3, "tenHP": "Môn nội bộ",
        }]
        references = [{
            "sourceId": "source", "mssv": "123", "namHoc": "2025-2026", "hocKy": "HK1", "maHP": "SOURCE",
            "diem10": 8, "diemChu": "B", "soTC": 3, "tenHP": "Môn nguồn",
        }]

        result = E.grade_review_assistance(
            {"errors": [], "warnings": [], "infos": []},
            current,
            [{"id": "source", "label": "Nguồn", "kind": "imported"}],
            references,
        )

        self.assertEqual(
            {item["kind"] for item in result["sourceComparisons"][0]["differences"]},
            {"not_in_reference", "missing_in_current"},
        )

    def test_reference_grade_import_rejects_incomplete_identity(self):
        with self.assertRaisesRegex(E.ProcessError, "Nguồn cũ chưa bị thay đổi"):
            E.normalize_reference_grades([{"mssv": "123", "diem_10": 8}])

    def test_tc04_thieu_diem_khoa_hieu_chinh(self):
        """TC04 g_diem(Không) → t_khoa → g_kh(Có) → g_mdc → t_doichieu → g_diem(Có) → t_tao"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521103"))
        self.assertEqual(r["status"], "CHO_KHOA")
        self.assertEqual(r["check"]["errors"][0]["code"], "D1")
        gid = r["check"]["errors"][0]["gradeId"]
        E.khoa_edit_grade(db, r["id"], gid, {"diem10": "8.0", "autoLetter": True}, KHOA)
        E.khoa_decide(db, r["id"], True, "Bổ sung điểm từ bảng điểm gốc", KHOA)
        self.assertEqual(r["status"], "CHO_KIEM_TRA")
        self.assertTrue(any(l["level"] == "audit" for l in db.logs), "Hiệu chỉnh điểm phải có nhật ký kiểm toán")

    def test_tc05_khoa_tu_choi(self):
        """TC05 t_khoa → g_kh(Không) → end_kh"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "241121506108"))
        self.assertEqual(r["check"]["errors"][0]["code"], "D0")
        E.khoa_decide(db, r["id"], False, "Sinh viên chưa hoàn thành học kỳ nào", KHOA)
        self.assertEqual(r["status"], "KHOA_TU_CHOI")
        self.assertTrue(any(m["step"] == "end_kh" for m in db.outbox))

    def test_tc06_nhac_khoa_sau_2_ngay(self):
        """TC06 t_khoa ⏱ b_khoa → t_nhackhoa → end_nhackhoa (không ngắt, nhắc 1 lần)"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121502105"))
        self.assertTrue(any(e["code"] == "D5" for e in r["check"]["errors"]))
        E.advance_clock(db, 2 * E.DAY + 1)
        self.assertEqual(r["status"], "CHO_KHOA")
        E.advance_clock(db, 3 * E.DAY)
        self.assertEqual(sum(1 for m in db.outbox if m["step"] == "t_nhackhoa"), 1)
        dup = next(e for e in r["check"]["errors"] if e["code"] == "D5")["gradeId"]
        E.khoa_edit_grade(db, r["id"], dup, {"delete": True}, KHOA)
        E.khoa_decide(db, r["id"], True, "", KHOA)
        self.assertEqual(r["status"], "CHO_KIEM_TRA")

    def test_tc07_diem_bat_thuong(self):
        """TC07 độ tin cậy 0.88 < 0.90 → t_khoa → xác nhận → g_kh(Có)"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121502106"))
        self.assertEqual(r["status"], "CHO_KHOA")
        self.assertEqual(len(r["check"]["errors"]), 0)
        self.assertEqual(len(r["check"]["warnings"]), 1)
        E.khoa_acknowledge(db, r["id"], r["check"]["warnings"][0]["key"], KHOA)
        E.khoa_decide(db, r["id"], True, "Điểm đúng thực tế", KHOA)
        self.assertEqual(r["status"], "CHO_KIEM_TRA")
        self.assertEqual(r["check"]["confidence"], 1)


class KiemTraVaPheDuyet(unittest.TestCase):
    def test_tc08_chua_dat_chinh_sua(self):
        """TC08 g_dat(Chưa đạt) → t_chinh → g_m2 → t_tao → g_dat(Đạt)"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121506109"))
        with self.assertRaises(E.ProcessError):
            E.qc_decide(db, r["id"], False, "", PDT)
        E.qc_decide(db, r["id"], False, "Cần bản tiếng Anh", PDT)
        self.assertEqual(r["status"], "CHO_CHINH_SUA")
        E.edit_transcript(db, r["id"], {"ngonNgu": "en"}, PDT)
        self.assertEqual(r["transcript"]["version"], 2)
        self.assertEqual(r["transcript"]["lang"], "en")
        E.qc_decide(db, r["id"], True, "", PDT)
        self.assertEqual(r["status"], "CHO_PHE_DUYET")

    def test_tc09_pho_phong_yeu_cau_chinh_sua(self):
        """TC09 g_pd(Yêu cầu chỉnh sửa) → t_chinh → t_tao → g_dat → t_pd → g_pd(Phê duyệt)"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521101"))
        E.qc_decide(db, r["id"], True, "", PDT)
        E.pp_decide(db, r["id"], "revise", "Ghi rõ mục đích sử dụng ở phần ghi chú", PP)
        self.assertEqual(r["status"], "CHO_CHINH_SUA")
        self.assertEqual(r["feedback"][-1]["from"], "Phó phòng")
        E.edit_transcript(db, r["id"], {"ghiChuBangDiem": "Cấp để nộp hồ sơ học bổng"}, PDT)
        E.qc_decide(db, r["id"], True, "", PDT)
        E.pp_decide(db, r["id"], "approve", "", PP)
        self.assertEqual(r["status"], "HOAN_TAT")

    def test_tc10_pho_phong_tu_choi(self):
        """TC10 t_pd → g_pd(Từ chối) → end_tuchoi"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521101"))
        E.qc_decide(db, r["id"], True, "", PDT)
        with self.assertRaises(E.ProcessError):
            E.pp_decide(db, r["id"], "reject", "", PP)  # bắt buộc ghi lý do
        E.pp_decide(db, r["id"], "reject", "Sinh viên đang bị xử lý kỷ luật thi", PP)
        self.assertEqual(r["status"], "PP_TU_CHOI")
        self.assertFalse(db.archive, "Không được ký số")

    def test_tc11_nhac_pho_phong_sau_1_ngay(self):
        """TC11 t_pd ⏱ b_pp → t_nhacpp → Event_1j9h9e1"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521101"))
        E.qc_decide(db, r["id"], True, "", PDT)
        E.advance_clock(db, 23 * E.HOUR)
        self.assertFalse(any(m["step"] == "t_nhacpp" for m in db.outbox))
        E.advance_clock(db, 2 * E.HOUR)
        self.assertTrue(any(m["step"] == "t_nhacpp" for m in db.outbox))
        self.assertEqual(r["status"], "CHO_PHE_DUYET")


class KySoVaGpa(unittest.TestCase):
    def test_tc14_ky_so_phat_hien_sua_doi(self):
        """TC14 t_dongdau: chữ ký RSA hợp lệ; sửa nội dung sau khi ký bị phát hiện"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521101"))
        E.qc_decide(db, r["id"], True, "", PDT)
        E.pp_decide(db, r["id"], "approve", "", PP)
        v1 = E.verify(db, r["signature"]["code"])
        self.assertTrue(v1["found"] and v1["valid"])
        db.archive[0]["transcript"]["summary"]["gpa4"] = 4
        v2 = E.verify(db, r["signature"]["code"])
        self.assertTrue(v2["found"])
        self.assertFalse(v2["valid"])
        self.assertFalse(E.verify(db, "ABCD-0000-1111")["found"])
        # Giả mạo chữ ký cũng bị phát hiện
        db.archive[0]["transcript"]["summary"]["gpa4"] = r["transcript"]["summary"]["gpa4"]
        self.assertTrue(E.verify(db, r["signature"]["code"])["valid"])
        db.archive[0]["signature"] = SIGNER.sign("0" * 64)
        self.assertFalse(E.verify(db, r["signature"]["code"])["valid"])

    def test_tc15_tinh_gpa(self):
        """TC15 học lại lấy điểm cao nhất; tín chỉ tích lũy chỉ tính môn đạt"""
        rows = [{"maHP": "A", "soTC": 3, "diem10": 3.8}, {"maHP": "A", "soTC": 3, "diem10": 6.6},
                {"maHP": "B", "soTC": 2, "diem10": 8.5}, {"maHP": "C", "soTC": 3, "diem10": 2.0}]
        s = E.compute_summary(rows)
        self.assertEqual(s["gpa4"], 1.94)
        self.assertEqual(s["tcTichLuy"], 5)


class NhanhMoiCuaBpmnDaSua(unittest.TestCase):
    def test_tc16_loi_truy_xuat_diem(self):
        """TC16 t_truyxuat ⚡ Boundary_LoiTruyXuat → Task_GhiNhanLoiTruyXuat → Task_ThongBaoLoiTruyXuat → End_LoiHeThong"""
        db = fresh_db()
        db.fault = True
        r = E.submit_request(db, form(db, "221121521101"))
        self.assertEqual(r["status"], "LOI_HE_THONG")
        self.assertEqual(steps(r)[-4:], ["Boundary_LoiTruyXuat", "Task_GhiNhanLoiTruyXuat", "Task_ThongBaoLoiTruyXuat", "End_LoiHeThong"])
        self.assertTrue(any(l["level"] == "error" for l in db.logs))
        self.assertTrue(any(m["step"] == "Task_ThongBaoLoiTruyXuat" for m in db.outbox))
        self.assertNotIn("t_doichieu", steps(r))
        db.fault = False  # sự cố được khắc phục → SV gửi lại thành công
        r2 = E.submit_request(db, form(db, "221121521101"))
        self.assertEqual(r2["status"], "CHO_KIEM_TRA")

    def test_tc17_sv_chu_dong_huy(self):
        """TC17 Event sub-process ngắt: Start_NhanThongDiepHuy → Task_EventCapNhatHuy → Task_EventGuiThongBaoHuy → End_EventHuy"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "221121521101"))
        E.qc_decide(db, r["id"], True, "", PDT)
        self.assertEqual(r["status"], "CHO_PHE_DUYET")
        E.student_cancel(db, r["id"], "Đã có bảng điểm bản cũ", "Trần Minh Anh")
        self.assertEqual(r["status"], "SV_HUY")
        self.assertEqual(steps(r)[-1], "End_EventHuy")
        self.assertEqual(r["timers"], {}, "Event sub-process ngắt phải dừng mọi timer")
        E.advance_clock(db, 2 * E.DAY)
        self.assertFalse(any(m["step"] == "t_nhacpp" for m in db.outbox), "Không còn nhắc Phó phòng sau khi hủy")
        with self.assertRaises(E.ProcessError):
            E.pp_decide(db, r["id"], "approve", "", PP)

    def test_tc18_khong_huy_sau_khi_ky_so(self):
        """TC18 Sau khi đã ký số (đang in bản giấy) thì SV không hủy được"""
        db = fresh_db()
        r = E.submit_request(db, form(db, "201121521107", banGiay=True, soBan=1))
        E.qc_decide(db, r["id"], True, "", PDT)
        E.pp_decide(db, r["id"], "approve", "", PP)
        with self.assertRaises(E.ProcessError):
            E.student_cancel(db, r["id"], "", "SV")

    def test_tc19_du_lieu_mau(self):
        """TC19 Dữ liệu mẫu chạy qua quy trình và kích hoạt timer đúng"""
        db = E.Db()
        db.signer = SIGNER
        S.populate_sample(db)
        st = {r["form"]["mssv"]: r["status"] for r in db.requests}
        self.assertEqual(st["221121521101"], "HOAN_TAT")
        self.assertEqual(st["201121521107"], "HOAN_TAT")
        self.assertEqual(st["221121521110"], "DA_HUY")
        self.assertEqual(st["221121521103"], "CHO_KHOA")
        self.assertEqual(st["221121502102"], "CHO_PHE_DUYET")
        self.assertTrue(any(m["step"] == "t_nhackhoa" for m in db.outbox))

    def test_tc20_du_lieu_demo_sau_nu_sinh_diem_deterministic(self):
        data = S.build_data()
        target_ids = {
            "241121521209": "Nam",
            "241121521220": "Nữ",
            "241121521229": "Nữ",
            "241121521230": "Nữ",
            "241121521243": "Nữ",
            "2421121521231": "Nữ",
        }
        students = {student["mssv"]: student for student in data["students"]}
        grades = [grade for grade in data["grades"] if grade["mssv"] in target_ids]

        self.assertEqual({mssv: students[mssv]["gioiTinh"] for mssv in target_ids}, target_ids)
        self.assertEqual(len(grades), len(target_ids) * 20)
        self.assertTrue(all(0 <= grade["diem10"] <= 10 for grade in grades))
        self.assertTrue(all(grade["diemChu"] == E.letter_of(grade["diem10"])["letter"] for grade in grades))


if __name__ == "__main__":
    unittest.main(verbosity=2)
