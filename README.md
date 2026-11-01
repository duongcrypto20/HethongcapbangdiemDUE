# Hệ thống cấp phát bảng điểm (TO-BE) — bản Python

Ứng dụng web hỗ trợ quy trình **"Xét duyệt và cấp phát bảng điểm (TO-BE)"** theo mô hình BPMN đã sửa của nhóm (`bpmn/BPMN_TO_BE_NHOM5_da_sua.bpmn`). Backend Python (Flask + SQLite), frontend HTML/CSS/JS, giao diện tông trắng – xanh theo cổng thông tin DUE.

> Dữ liệu mẫu là hư cấu. Bảng điểm sinh ra luôn có dấu chìm "BẢN DEMO – KHÔNG CÓ GIÁ TRỊ PHÁP LÝ".

## Chạy ứng dụng

Yêu cầu: Python 3.10 trở lên.

**Cách nhanh nhất**: Windows bấm đúp `chay.bat`; macOS/Linux chạy `./chay.sh`. Script tự tạo môi trường ảo, cài thư viện và mở `http://127.0.0.1:5000`.

**Chạy tay**:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py                   # mở http://127.0.0.1:5000
```

Lần chạy đầu, hệ thống tự tạo CSDL `data/bangdiem.db` với dữ liệu mẫu và sinh cặp khóa ký số trong `keys/`.

### Tài khoản demo chính (mật khẩu `123456`)

| Vai trò | Tên đăng nhập |
|---|---|
| Sinh viên | `241121521209` (Ngô Quỳnh Dương), `241121521229` (Võ Trương Gia Nghi), `2421121521231` (Lê Thị Thanh Nhàn), `241121521243` (Trần Tôn Phương Thảo), `241121521230` (Đinh Thị Mỹ Ngọc), `241121521220` (Võ Thị Lạc) |
| Khoa | `khoa.thongketinhoc`, `khoa.quantrikinhdoanh`, `khoa.ketoan` |
| Phòng Đào tạo | `pdt.hong` |
| Phó phòng | `pp.lethi` |

Trang đăng nhập liệt kê sẵn các tài khoản demo và kịch bản kiểm thử; bấm vào để đăng nhập nhanh.

## Kiểm thử tự động

```bash
python -m unittest discover -s tests -v
```

- `tests/test_quy_trinh.py`: 19 kịch bản, mỗi kịch bản đi một nhánh BPMN (5 cổng XOR, cổng bao hàm, 3 timer, nhánh lỗi truy xuất, event sub-process SV hủy, ký số, tính GPA).
- `tests/test_api.py`: 9 kiểm thử API (đăng nhập, khóa sau 5 lần sai, phân quyền theo làn, CSRF, lưu bền vững sau khởi động lại, tra cứu chữ ký, nhập CSV).

Phòng Đào tạo cũng chạy được bộ kịch bản quy trình ngay trên web: **Hệ thống & dữ liệu › Kiểm thử tự động**.

## Kịch bản demo nhanh

| # | Đăng nhập | Thao tác | Phần tử BPMN |
|---|---|---|---|
| 1 | SV `221121506109` | Tạo yêu cầu, chọn thêm 2 bản giấy | `s_task → ca_xt → t_truyxuat → t_doichieu → t_tao` |
| 2 | `pdt.hong` | Phòng Đào tạo › Chờ kiểm tra › Đạt | `g_dat → t_pd` |
| 3 | `pp.lethi` | Phê duyệt & ký số (nhận mã xác thực) | `g_pd → t_dongdau → Gateway_0m52u6m → t_guidt` |
| 4 | `pdt.hong`, `pp.lethi` | In → Đóng dấu → Xác nhận đã giao | `t_in → Activity_0xvx345 → Activity_15aejsy → t_nhatky → end_ht` |
| 5 | Không cần | Tra cứu › nhập mã xác thực | Kiểm chứng chữ ký RSA |
| 6 | `khoa.quantrikinhdoanh` | Rà soát điểm bất thường của Huỳnh Quốc Nam › Xác nhận › Đã hiệu chỉnh | `t_khoa → g_kh(Có) → g_mdc` |
| 7 | SV `221121521103` | Mở yêu cầu đang chờ Khoa › Hủy yêu cầu | `EventSub_SVChuDongHuy` |
| 8 | `pdt.hong` | Hệ thống › Bật giả lập sự cố, rồi SV gửi yêu cầu mới | `Boundary_LoiTruyXuat → End_LoiHeThong` |
| 9 | Bất kỳ | Nút **+1 ngày** trên cùng (bấm 3 lần) | `e_t3`, `b_khoa`, `b_pp` |

## Dùng dữ liệu test của giảng viên

1. Đăng nhập `pdt.hong` › **Hệ thống & dữ liệu › Khôi phục dữ liệu** › "Xóa sạch để nạp dữ liệu giảng viên" (bấm 2 lần).
2. **CSDL sinh viên**: dán CSV hoặc chọn tệp. Cột `mssv, ho_ten, ngay_sinh, gioi_tinh, lop, khoa, nganh, khoa_hoc, email, trang_thai`. Mỗi sinh viên được tạo tài khoản SSO (tên đăng nhập = MSSV), mỗi Khoa mới được tạo tài khoản văn phòng Khoa.
3. **CSDL điểm**: cột `mssv, nam_hoc, hoc_ky, ma_hp, ten_hp, so_tc, diem_10, diem_chu`.
4. **Nhập yêu cầu hàng loạt**: cột `mssv, ho_ten, ngay_sinh, email, sdt, muc_dich, ngon_ngu, ban_giay, so_ban`.

Tiêu đề cột chấp nhận tiếng Việt có dấu; dấu phân cách phẩy, chấm phẩy hoặc tab. Tệp mẫu nằm trong `data/`.

## Cấu hình (tệp `.env`, xem `.env.example`)

| Biến | Ý nghĩa |
|---|---|
| `SIGN_KEY_PASSPHRASE` | Passphrase mã hóa khóa bí mật ký số. **Đổi khi triển khai thật.** |
| `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | Kết nối Turso bền vững; để trống thì dùng SQLite local. |
| `FLASK_SECRET_KEY` | Khóa ký cookie phiên; cần giữ ổn định trên Vercel. |
| `SIGNING_PRIVATE_KEY_B64` | Khóa RSA riêng PEM đã mã hóa, Base64; cần giữ ổn định để chữ ký xác minh được giữa các instance. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Gửi email thật (vd. Gmail `smtp.gmail.com:587` + mật khẩu ứng dụng). Để trống thì email chỉ lưu trong hộp thư hệ thống. |
| `SMTP_REDIRECT_TO` | Khi demo, chuyển mọi email tới một địa chỉ của nhóm |
| `DEMO_MODE` | `1`: hiện tài khoản demo và nút tua đồng hồ; `0`: tắt |
| `COOKIE_SECURE` | `1` khi chạy sau HTTPS |

## Cấu trúc mã nguồn

```
app.py                    Flask: REST API, xác thực, phân quyền theo làn, phục vụ giao diện
bangdiem/bpmn.py          Danh mục phần tử BPMN, trạng thái ↔ vị trí token, đọc sequenceFlow
bangdiem/engine.py        Bộ máy quy trình: luật X1–X8, D0–D7, cổng XOR, timer, GPA, hủy, lỗi truy xuất
bangdiem/store.py         Lưu trữ SQLite (giao dịch), tài khoản
bangdiem/schema.sql       Lược đồ CSDL
bangdiem/signing.py       Ký số RSA-PSS, quản lý khóa
bangdiem/mailer.py        Email: hộp thư + SMTP
bangdiem/seed.py          Dữ liệu mẫu
bangdiem/csvio.py         Đọc CSV/JSON dữ liệu test
static/                   Giao diện (index.html, css/style.css, js/app.js, logo, sơ đồ BPMN)
bpmn/                     Tệp BPMN to-be đã sửa và SVG gốc
tests/                    Kiểm thử tự động
data/                     CSV mẫu (CSDL SQLite được tạo tại đây khi chạy)
docs/thiet-ke.md          Thiết kế: ERD, màn hình, ánh xạ BPMN, công nghệ, quyết định kiến trúc
```

Nguyên tắc: **mọi thay đổi trạng thái đi qua `engine.py`**, mỗi hàm ứng với một phần tử BPMN và ghi id phần tử vào lịch sử. `app.py` chỉ xác thực, phân quyền, gọi engine và lưu; giao diện chỉ hiển thị.

## Giới hạn đã biết

- SSO là mô phỏng (đăng nhập bằng MSSV + mật khẩu), chưa kết nối máy chủ SSO thật của trường.
- Ký số dùng cặp khóa RSA tự sinh, chưa phải chứng thư số do tổ chức được cấp phép phát hành; "đóng dấu đỏ" là thao tác xác nhận trên hệ thống.
- SQLite và khóa ghi toàn cục phù hợp quy mô một trường; quy mô lớn hơn nên chuyển sang PostgreSQL.
- Vercel cần cấu hình `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `FLASK_SECRET_KEY`, `SIGN_KEY_PASSPHRASE` và `SIGNING_PRIVATE_KEY_B64` trong Project Settings › Environment Variables. Tạo khóa RSA ổn định local rồi Base64 hóa `keys/signing_key.pem`; không đưa token hoặc khóa riêng vào Git.
- Khóa ghi hiện chỉ tuần tự hóa yêu cầu trong cùng một process. Trước khi dùng nhiều người đồng thời trên serverless, cần bổ sung cơ chế chống ghi đè giữa các instance.
