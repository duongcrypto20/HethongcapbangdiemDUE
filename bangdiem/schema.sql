PRAGMA foreign_keys = ON;

-- Tài khoản đăng nhập & phân quyền theo 4 làn BPMN
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,                 -- PBKDF2/scrypt (werkzeug), không lưu mật khẩu gốc
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('SV', 'KHOA', 'PDT', 'PP')),
    department    TEXT,                          -- với vai trò KHOA: tên Khoa quản lý
    mssv          TEXT,                          -- với vai trò SV: liên kết logic tới students.mssv
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_users_full_name ON users(full_name);

-- CSDL sinh viên (data store "CSDL sinh viên" trong BPMN)
CREATE TABLE IF NOT EXISTS students (
    mssv       TEXT PRIMARY KEY,
    ho_ten     TEXT NOT NULL,
    ngay_sinh  TEXT,                -- yyyy-mm-dd
    gioi_tinh  TEXT,
    lop        TEXT,
    khoa       TEXT,                -- Khoa quản lý → dùng để phân quyền vai trò KHOA
    nganh      TEXT,
    khoa_hoc   TEXT,
    email      TEXT,
    trang_thai TEXT NOT NULL DEFAULT 'Đang học'
);

-- CSDL điểm (data store "CSDL điểm")
CREATE TABLE IF NOT EXISTS grades (
    id       TEXT PRIMARY KEY,
    mssv     TEXT NOT NULL,          -- liên kết logic tới students.mssv (cho phép nhập điểm trước khi có SV)
    nam_hoc  TEXT NOT NULL,
    hoc_ky   TEXT NOT NULL,
    ma_hp    TEXT,
    ten_hp   TEXT,
    so_tc    REAL,
    diem_10  REAL,                  -- NULL = thiếu điểm; giá trị chữ lỗi được giữ nguyên để luật D2 phát hiện
    diem_chu TEXT
);
CREATE INDEX IF NOT EXISTS ix_grades_mssv ON grades(mssv);

-- Nguồn điểm tham chiếu tách biệt; chỉ PĐT được thay nguồn qua API quản trị.
CREATE TABLE IF NOT EXISTS grade_reference_sources (
    source_id  TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS grade_reference_grades (
    source_id TEXT NOT NULL REFERENCES grade_reference_sources(source_id) ON DELETE CASCADE,
    row_no    INTEGER NOT NULL,
    mssv      TEXT NOT NULL,
    nam_hoc   TEXT NOT NULL,
    hoc_ky    TEXT NOT NULL,
    ma_hp     TEXT NOT NULL,
    ten_hp    TEXT,
    so_tc     TEXT,
    diem_10   TEXT,
    diem_chu  TEXT,
    PRIMARY KEY (source_id, row_no)
);
CREATE INDEX IF NOT EXISTS ix_grade_reference_lookup
    ON grade_reference_grades(source_id, mssv, nam_hoc, hoc_ky, ma_hp);

-- Yêu cầu cấp bảng điểm = một thể hiện (instance) của quy trình
CREATE TABLE IF NOT EXISTS requests (
    id                  TEXT PRIMARY KEY,           -- BD{năm}-{số thứ tự}
    mssv                TEXT NOT NULL,
    status              TEXT NOT NULL,              -- vị trí token trên BPMN (xem bangdiem/bpmn.py)
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 0, -- số lần xác thực (gửi + bổ sung)
    transcript_versions INTEGER NOT NULL DEFAULT 0,
    decision_note       TEXT,
    approved_by         TEXT,
    form_json           TEXT NOT NULL,              -- dữ liệu SV khai trên form
    options_json        TEXT,                       -- tùy chọn bảng điểm (ghi chú, người ký, học kỳ ẩn)
    validation_json     TEXT,                       -- kết quả luật X1–X8
    check_json          TEXT,                       -- kết quả đối chiếu D0–D7, A1, độ tin cậy
    acks_json           TEXT,
    transcript_json     TEXT,                       -- bảng điểm điện tử (bản mới nhất)
    auto_checks_json    TEXT,
    feedback_json       TEXT,                       -- góp ý của PĐT / Phó phòng
    signature_json      TEXT,
    timers_json         TEXT,                       -- hạn của các timer biên e_t3, b_khoa, b_pp
    paper_json          TEXT,
    branches_json       TEXT,                       -- trạng thái 2 nhánh của cổng bao hàm
    student_snapshot_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_requests_mssv ON requests(mssv);
CREATE INDEX IF NOT EXISTS ix_requests_status ON requests(status);

-- Lịch sử đi qua các phần tử BPMN (audit trail của từng yêu cầu)
CREATE TABLE IF NOT EXISTS request_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL,
    t          INTEGER NOT NULL,
    step       TEXT NOT NULL,       -- id phần tử BPMN, vd. ca_xt, g_diem
    actor      TEXT,
    note       TEXT,
    kind       TEXT
);
CREATE INDEX IF NOT EXISTS ix_history_req ON request_history(request_id, seq);

-- Email do hệ thống gửi (hộp thư; gửi SMTP thật nếu được cấu hình)
CREATE TABLE IF NOT EXISTS emails (
    id         INTEGER PRIMARY KEY,
    t          INTEGER NOT NULL,
    to_addr    TEXT,
    to_role    TEXT,
    subject    TEXT,
    body       TEXT,
    request_id TEXT REFERENCES requests(id) ON DELETE SET NULL,
    step       TEXT,
    delivery   TEXT
);

-- Nhật ký hệ thống / kiểm toán (hủy, hiệu chỉnh điểm, sự cố)
CREATE TABLE IF NOT EXISTS audit_logs (
    id         INTEGER PRIMARY KEY,
    t          INTEGER NOT NULL,
    level      TEXT NOT NULL,       -- info | warn | audit | error
    msg        TEXT NOT NULL,
    request_id TEXT,
    actor      TEXT
);

-- Kho bảng điểm đã ký số (data object "Bảng điểm điện tử [đã ký số]")
CREATE TABLE IF NOT EXISTS signed_transcripts (
    code            TEXT PRIMARY KEY,     -- mã xác thực XXXX-XXXX-XXXX
    request_id      TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    mssv            TEXT NOT NULL,
    hash            TEXT NOT NULL,        -- SHA-256 của nội dung JSON chuẩn hóa
    signature       TEXT NOT NULL,        -- chữ ký RSA-PSS (base64)
    key_id          TEXT,
    signed_at       INTEGER NOT NULL,
    transcript_json TEXT NOT NULL
);

-- Sổ cấp phát (task "Ghi nhật ký cấp phát")
CREATE TABLE IF NOT EXISTS issuance (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    t            INTEGER NOT NULL,
    request_id   TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    mssv         TEXT NOT NULL,
    ho_ten       TEXT,
    code         TEXT REFERENCES signed_transcripts(code),
    so_ban_giay  INTEGER NOT NULL DEFAULT 0,
    muc_dich     TEXT,
    approved_by  TEXT,
    lead_time_h  REAL
);

-- Tham số hệ thống: cấu hình ngưỡng, bộ đếm, đồng hồ mô phỏng, cờ giả lập sự cố
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
