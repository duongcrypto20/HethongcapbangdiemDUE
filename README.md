# Hệ thống cấp phát bảng điểm (TO-BE) — bản Python

Ứng dụng web hỗ trợ quy trình **"Xét duyệt và cấp phát bảng điểm (TO-BE)"** theo mô hình BPMN đã sửa của nhóm (`bpmn/BPMN_TO_BE_NHOM5_da_sua.bpmn`). Backend Python (Flask + SQLite local hoặc Turso trực tuyến), frontend HTML/CSS/JS, giao diện tông trắng – xanh theo cổng thông tin DUE.

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

### Tài khoản demo chính

Sinh viên dùng họ và tên làm tên đăng nhập, MSSV làm mật khẩu. Tài khoản cán bộ dùng mật khẩu demo chung `123456`.

| Vai trò | Tên đăng nhập |
|---|---|
| Sinh viên | `Ngô Quỳnh Dương` / `241121521209`, `Võ Trương Gia Nghi` / `241121521229`, `Lê Thị Thanh Nhàn` / `2421121521231`, `Trần Tôn Phương Thảo` / `241121521243`, `Đinh Thị Mỹ Ngọc` / `241121521230`, `Võ Thị Lạc` / `241121521220` |
| Khoa | `khoa.thongketinhoc`, `khoa.quantrikinhdoanh`, `khoa.ketoan` |
| Phòng Đào tạo | `pdt.hong` |
| Phó phòng | `pp.lethi` |

Trang đăng nhập liệt kê sẵn các tài khoản demo và kịch bản kiểm thử; bấm vào để đăng nhập nhanh. Chế độ này chỉ phù hợp với dữ liệu mẫu, không bật khi triển khai dữ liệu thật.

## Kiểm thử tự động

```bash
python -m unittest discover -s tests -v
```

- `tests/test_quy_trinh.py`: kiểm thử các nhánh BPMN, luật điểm, ký số, GPA và rà soát so sánh nguồn.
- `tests/test_api.py`: kiểm thử đăng nhập, phân quyền, CSRF, lưu bền vững, API và nhập nguồn tham chiếu.
- `tests/test_turso_store.py`: kiểm thử giao dịch và lưu trữ SQLite/Turso, cấu hình triển khai.

Phòng Đào tạo cũng chạy được bộ kịch bản quy trình ngay trên web: **Hệ thống & dữ liệu › Kiểm thử tự động**.

## Hỗ trợ Khoa rà soát điểm

Khi yêu cầu cần Khoa xử lý, màn hình chi tiết hiển thị luật D0-D7/A1/I1, so sánh các dòng điểm với một nguồn tham chiếu được lưu tách biệt, nêu sai khác và nguyên nhân khả dĩ theo mẫu luật, rồi tạo nháp ghi chú để Khoa xem lại. Không dùng LLM/API AI bên ngoài. Nguồn ban đầu là dữ liệu tổng hợp phục vụ demo, không phải dữ liệu chính thức; PĐT có thể thay nguồn này bằng CSV đã được phê duyệt trong **Hệ thống & dữ liệu › CSDL điểm › Nạp nguồn tham chiếu riêng**. Phân tích chỉ đọc, không tự sửa điểm; nguyên nhân chỉ là giả thuyết, Khoa phải đối chiếu hồ sơ chính thức và quyết định.

## Kịch bản demo nhanh

| # | Đăng nhập | Thao tác | Phần tử BPMN |
|---|---|---|---|
| 1 | SV `Trương Mỹ Duyên` (mật khẩu `221121506109`) | Tạo yêu cầu, chọn thêm 2 bản giấy | `s_task → ca_xt → t_truyxuat → t_doichieu → t_tao` |
| 2 | `pdt.hong` | Phòng Đào tạo › Chờ kiểm tra › Đạt | `g_dat → t_pd` |
| 3 | `pp.lethi` | Phê duyệt & ký số (nhận mã xác thực) | `g_pd → t_dongdau → Gateway_0m52u6m → t_guidt` |
| 4 | `pdt.hong`, `pp.lethi` | In → Đóng dấu → Xác nhận đã giao | `t_in → Activity_0xvx345 → Activity_15aejsy → t_nhatky → end_ht` |
| 5 | Không cần | Tra cứu › nhập mã xác thực | Kiểm chứng chữ ký RSA |
| 6 | `khoa.quantrikinhdoanh` | Rà soát điểm bất thường của Huỳnh Quốc Nam › Xác nhận › Đã hiệu chỉnh | `t_khoa → g_kh(Có) → g_mdc` |
| 7 | SV `Phạm Gia Hân` (mật khẩu `221121521103`) | Mở yêu cầu đang chờ Khoa › Hủy yêu cầu | `EventSub_SVChuDongHuy` |
| 8 | `pdt.hong` | Hệ thống › Bật giả lập sự cố, rồi SV gửi yêu cầu mới | `Boundary_LoiTruyXuat → End_LoiHeThong` |
| 9 | Bất kỳ | Nút **+1 ngày** trên cùng (bấm 3 lần) | `e_t3`, `b_khoa`, `b_pp` |

## Dùng dữ liệu test của giảng viên

Các tài khoản demo Ngô Quỳnh Dương, Võ Thị Lạc, Võ Trương Gia Nghi, Đinh Thị Mỹ Ngọc,
Trần Tôn Phương Thảo và Lê Thị Thanh Nhàn có dữ liệu điểm hư cấu, được sinh xác định
để phục vụ demo. Dương được ghi giới tính Nam; các tài khoản còn lại ghi Nữ. Không dùng
dữ liệu demo làm kết quả học tập thật. Có thể nạp các hồ sơ và điểm này từ hai tệp
`data/demo-sinh-vien-bo-sung.csv` và `data/demo-diem-bo-sung.csv`.

1. Đăng nhập `pdt.hong` › **Hệ thống & dữ liệu › Khôi phục dữ liệu** › "Xóa sạch để nạp dữ liệu giảng viên" (bấm 2 lần).
2. **CSDL sinh viên**: dán CSV hoặc chọn tệp. Cột `mssv, ho_ten, ngay_sinh, gioi_tinh, lop, khoa, nganh, khoa_hoc, email, trang_thai`. Mỗi sinh viên được tạo tài khoản đăng nhập bằng họ tên (mật khẩu là MSSV), mỗi Khoa mới được tạo tài khoản văn phòng Khoa.
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
| `DEMO_MODE` | `1`: hiện tài khoản demo và nút tua đồng hồ; sinh viên đăng nhập bằng họ tên với mật khẩu là MSSV, cán bộ dùng `123456`. `0`: ẩn tài khoản demo và tắt nút tua đồng hồ. Chỉ bật với dữ liệu mẫu. |
| `COOKIE_SECURE` | `1` khi chạy sau HTTPS |

## Cấu trúc mã nguồn

```
app.py                    Flask: REST API, xác thực, phân quyền theo làn, phục vụ giao diện
bangdiem/bpmn.py          Danh mục phần tử BPMN, trạng thái ↔ vị trí token, đọc sequenceFlow
bangdiem/engine.py        Bộ máy quy trình: luật X1–X8, D0–D7, cổng XOR, timer, GPA, hủy, lỗi truy xuất
bangdiem/store.py         Lưu trữ SQLite/Turso (giao dịch, đọc Turso theo lô), tài khoản
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
- Vercel cần cấu hình `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `FLASK_SECRET_KEY`, `SIGN_KEY_PASSPHRASE` và `SIGNING_PRIVATE_KEY_B64` trong Project Settings › Environment Variables. Function chạy tại Singapore (`sin1`), gần Turso `ap-southeast-1` để giảm độ trễ. Tạo khóa RSA ổn định local rồi Base64 hóa `keys/signing_key.pem`; không đưa token hoặc khóa riêng vào Git.
- Mỗi thao tác ghi lấy khóa giao dịch ở cơ sở dữ liệu trước khi đọc snapshot; thao tác chỉ đọc không ghi lại toàn bộ dữ liệu. Điều này ngăn các instance Vercel ghi đè snapshot của nhau. Với tải ghi lớn hơn, nên chuyển sang PostgreSQL.
