from __future__ import annotations

import re
from pathlib import Path

LANES = {
    "SV": "Sinh viên",
    "KHOA": "Khoa",
    "PDT": "Phòng Đào tạo",
    "PP": "Phó phòng",
}

# id phần tử -> tên hiển thị, làn, loại
STEPS = {
    # Luồng chính
    "s_start": ("Cần bảng điểm", "SV", "start"),
    "s_task": ("Đăng nhập SSO & điền yêu cầu", "SV", "user"),
    "g_m1": ("Gộp yêu cầu mới / bổ sung", "PDT", "gateway"),
    "ca_xt": ("Xác thực & kiểm tra thông tin SV", "PDT", "service"),
    "g_hl": ("Thông tin hợp lệ?", "PDT", "gateway"),
    "Activity_0ze94gf": ("Yêu cầu SV bổ sung (email tự động)", "PDT", "send"),
    "s_bs_task": ("Bổ sung thông tin trực tuyến", "SV", "user"),
    "e_t3": ("Quá 3 ngày", "SV", "timer"),
    "t_huy": ("Hủy yêu cầu & lưu log", "PDT", "service"),
    "t_guihuy": ("Gửi thông báo hủy yêu cầu (email)", "PDT", "send"),
    "s_nhan_huy": ("Nhận thông báo hủy yêu cầu", "SV", "receive"),
    "s_end_huy": ("Yêu cầu đã hủy (quá hạn bổ sung)", "SV", "end"),
    "t_truyxuat": ("Truy xuất điểm theo từng học kỳ", "PDT", "service"),
    "Boundary_LoiTruyXuat": ("Lỗi truy xuất", "PDT", "error"),
    "Task_GhiNhanLoiTruyXuat": ("Ghi nhận sự cố truy xuất", "PDT", "service"),
    "Task_ThongBaoLoiTruyXuat": ("Thông báo sinh viên thử lại sau", "PDT", "send"),
    "End_LoiHeThong": ("Dừng do lỗi hệ thống", "PDT", "end"),
    "g_mdc": ("Gộp luồng đối chiếu", "PDT", "gateway"),
    "t_doichieu": ("Đối chiếu & kiểm tra điểm tự động", "PDT", "rule"),
    "g_diem": ("Điểm đầy đủ, chính xác?", "PDT", "gateway"),
    "t_khoa": ("Rà soát & hiệu chỉnh điểm", "KHOA", "user"),
    "b_khoa": ("Sau 2 ngày", "KHOA", "timer"),
    "t_nhackhoa": ("Nhắc Khoa xử lý (tự động)", "PDT", "send"),
    "end_nhackhoa": ("Đã nhắc Khoa", "PDT", "end"),
    "g_kh": ("Khoa hiệu chỉnh được?", "KHOA", "gateway"),
    "end_kh": ("Từ chối cấp bảng điểm", "KHOA", "end"),
    "g_m2": ("Gộp tạo / chỉnh sửa", "PDT", "gateway"),
    "t_tao": ("Tạo bảng điểm điện tử", "PDT", "service"),
    "g_dat": ("Bảng điểm đạt yêu cầu?", "PDT", "gateway"),
    "t_chinh": ("Chỉnh sửa theo góp ý", "PDT", "user"),
    "t_pd": ("Xem xét bảng điểm", "PP", "user"),
    "b_pp": ("Sau 1 ngày", "PP", "timer"),
    "t_nhacpp": ("Nhắc Phó phòng (tự động)", "PDT", "send"),
    "Event_1j9h9e1": ("Đã nhắc Phó phòng", "PDT", "end"),
    "g_pd": ("Phó phòng quyết định?", "PP", "gateway"),
    "end_tuchoi": ("Yêu cầu bị từ chối", "PP", "end"),
    "t_dongdau": ("Ký số & lưu trữ bảng điểm", "PDT", "service"),
    "Gateway_0m52u6m": ("Hình thức nhận bảng điểm?", "PDT", "gateway"),
    "t_guidt": ("Gửi bảng điểm điện tử (email)", "PDT", "send"),
    "t_in": ("In bản giấy", "PDT", "user"),
    "Activity_0xvx345": ("Đóng dấu đỏ xác nhận", "PP", "manual"),
    "Activity_15aejsy": ("Xác nhận đã cấp bản giấy", "PDT", "user"),
    "Gateway_198pqrp": ("Gộp nhánh cấp phát", "PDT", "gateway"),
    "t_nhatky": ("Ghi nhật ký cấp phát", "PDT", "service"),
    "end_ht": ("Bảng điểm đã được cấp", "PDT", "end"),
    # Event sub-process: sinh viên chủ động hủy (ngắt luồng chính)
    "EventSub_SVChuDongHuy": ("Ngoại lệ: sinh viên chủ động hủy yêu cầu", "PDT", "subprocess"),
    "Start_NhanThongDiepHuy": ("SV yêu cầu hủy", "PDT", "message-start"),
    "Task_EventCapNhatHuy": ("Hủy hồ sơ và ghi nhật ký", "PDT", "service"),
    "Task_EventGuiThongBaoHuy": ("Gửi xác nhận đã hủy", "PDT", "send"),
    "End_EventHuy": ("Yêu cầu đã hủy (SV chủ động)", "PDT", "end"),
}

# Trạng thái chờ của yêu cầu = token đang nằm ở phần tử BPMN nào
STATUS = {
    "CHO_BO_SUNG": {"label": "Chờ SV bổ sung", "step": "s_bs_task", "role": "SV", "tone": "warn"},
    "CHO_KHOA": {"label": "Chờ Khoa rà soát", "step": "t_khoa", "role": "KHOA", "tone": "warn"},
    "CHO_KIEM_TRA": {"label": "Chờ kiểm tra bảng điểm", "step": "g_dat", "role": "PDT", "tone": "info"},
    "CHO_CHINH_SUA": {"label": "Chờ chỉnh sửa theo góp ý", "step": "t_chinh", "role": "PDT", "tone": "warn"},
    "CHO_PHE_DUYET": {"label": "Chờ Phó phòng duyệt", "step": "t_pd", "role": "PP", "tone": "info"},
    "CHO_IN": {"label": "Chờ in bản giấy", "step": "t_in", "role": "PDT", "tone": "info"},
    "CHO_DONG_DAU": {"label": "Chờ đóng dấu đỏ", "step": "Activity_0xvx345", "role": "PP", "tone": "info"},
    "CHO_XAC_NHAN_GIAY": {"label": "Chờ xác nhận cấp bản giấy", "step": "Activity_15aejsy", "role": "PDT", "tone": "info"},
    "HOAN_TAT": {"label": "Bảng điểm đã được cấp", "step": "end_ht", "final": True, "tone": "ok"},
    "DA_HUY": {"label": "Đã hủy (quá hạn bổ sung)", "step": "s_end_huy", "final": True, "tone": "bad"},
    "SV_HUY": {"label": "Đã hủy (SV chủ động)", "step": "End_EventHuy", "final": True, "tone": "bad"},
    "KHOA_TU_CHOI": {"label": "Khoa từ chối cấp", "step": "end_kh", "final": True, "tone": "bad"},
    "PP_TU_CHOI": {"label": "Phó phòng từ chối", "step": "end_tuchoi", "final": True, "tone": "bad"},
    "LOI_HE_THONG": {"label": "Dừng do lỗi hệ thống", "step": "End_LoiHeThong", "final": True, "tone": "bad"},
}

# Các trạng thái SV còn được chủ động hủy (event sub-process ngắt).
# Sau khi đã ký số và gửi bản điện tử thì không hủy được nữa.
CANCELLABLE = ("CHO_BO_SUNG", "CHO_KHOA", "CHO_KIEM_TRA", "CHO_CHINH_SUA", "CHO_PHE_DUYET")

TYPE_LABEL = {
    "user": "User task", "service": "Service task", "rule": "Business rule task", "send": "Send task",
    "receive": "Receive task", "manual": "Manual task", "gateway": "Cổng", "timer": "Timer biên",
    "error": "Error biên", "start": "Sự kiện bắt đầu", "message-start": "Bắt đầu (message)",
    "end": "Sự kiện kết thúc", "subprocess": "Event sub-process",
}


def step_name(step_id: str) -> str:
    s = STEPS.get(step_id)
    return s[0] if s else step_id


def step_type(step_id: str) -> str:
    s = STEPS.get(step_id)
    return s[2] if s else "task"


def parse_flows(bpmn_path: Path) -> list[dict]:
    """Đọc các sequenceFlow trong tệp .bpmn để giao diện tô sáng đường đi."""
    text = Path(bpmn_path).read_text(encoding="utf-8")
    flows = []
    for m in re.finditer(r"<bpmn:sequenceFlow\b([^>]*)>", text):
        attrs = m.group(1)

        def g(k: str) -> str | None:
            mm = re.search(rf'\b{k}="([^"]*)"', attrs)
            return mm.group(1) if mm else None

        flows.append({"id": g("id"), "s": g("sourceRef"), "t": g("targetRef"), "name": g("name")})
    return flows


def catalog() -> dict:
    """Danh mục gửi cho giao diện."""
    return {
        "lanes": LANES,
        "steps": {k: {"name": v[0], "lane": v[1], "type": v[2]} for k, v in STEPS.items()},
        "status": STATUS,
        "cancellable": list(CANCELLABLE),
        "typeLabel": TYPE_LABEL,
    }
