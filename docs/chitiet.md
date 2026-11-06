# Chi tiết mã nguồn và chức năng

Tài liệu này giới thiệu các tệp chính của repository, vai trò của từng tệp và các đoạn code quan trọng. Mã nguồn thuộc một ứng dụng Flask với giao diện HTML/CSS/JavaScript, bộ máy quy trình nghiệp vụ BPMN, lưu trữ SQLite/Turso và kiểm thử bằng `unittest`.

## 1. Tổng quan cách các thành phần hoạt động

```text
Trình duyệt
  static/index.html + static/css/style.css + static/js/app.js
                       │ gọi API
                       ▼
             app.py (Flask, xác thực, phân quyền)
                       │
         ┌─────────────┴──────────────┐
         ▼                            ▼
 bangdiem/engine.py              bangdiem/store.py
 luật và quy trình               SQLite hoặc Turso
         │                            └── schema.sql
         ├── bpmn.py
         ├── signing.py
         ├── mailer.py
         └── csvio.py
```

Khi chạy cục bộ, `app.py` tạo ứng dụng Flask; dữ liệu thường được lưu ở `data/bangdiem.db`. Trên Vercel, `api/index.py` xuất ứng dụng Flask và cấu hình triển khai được mô tả trong `vercel.json`. Quy trình nghiệp vụ, trạng thái và luật kiểm tra tập trung trong `bangdiem/engine.py`.

## 2. Backend và nghiệp vụ

### `app.py` — ứng dụng Flask và API

Điểm vào khi chạy cục bộ (`python app.py`) và nơi đăng ký API cho giao diện.

- `create_app(...)`: tạo Flask app, nạp cấu hình, khởi tạo store/ký số/email, đăng ký route và phục vụ tệp giao diện.
- Các route API xử lý đăng nhập/đăng xuất, trạng thái ứng dụng, yêu cầu cấp bảng điểm, rà soát, phê duyệt, ký số, tra cứu mã và chức năng quản trị.
- Các hàm kiểm tra đăng nhập, vai trò và phạm vi dữ liệu bảo vệ route; ví dụ sinh viên chỉ thao tác với yêu cầu của mình, Khoa chỉ xử lý phạm vi Khoa.
- Route chi tiết yêu cầu ở khoảng dòng 399–414 tạo `liveCheck` cho nhân viên. Chỉ khi `role == "KHOA"` và trạng thái `CHO_KHOA`, API mới trả thêm `reviewAssistant`.
- Phần cuối file có xử lý phiên giao dịch và retry phù hợp với store.

### `bangdiem/engine.py` — bộ máy quy trình và luật nghiệp vụ

Đây là module nghiệp vụ chính. Các hàm nhận đối tượng CSDL đang nạp, xác thực trạng thái trước khi thực hiện thao tác, cập nhật lịch sử và trạng thái quy trình.

- `Db`, `ProcessError`: cấu trúc trạng thái đang xử lý và lỗi nghiệp vụ có mã HTTP.
- Nhóm chuẩn hóa/kiểm tra dữ liệu: chuẩn hóa tên/ngày/điểm, tính độ tương đồng tên, ánh xạ điểm số sang điểm chữ và tính mã băm.
- Nhóm quy trình: gửi yêu cầu, xác thực thông tin, bổ sung, truy xuất điểm, đối chiếu, Khoa xử lý, PĐT kiểm tra/chỉnh sửa, Phó phòng phê duyệt.
- Nhóm cấp bảng điểm: tạo bảng điểm, ký số, gửi bản điện tử, in/đóng dấu/xác nhận bản giấy, ghi sổ cấp phát.
- `tick(...)`: xử lý timer và các sự kiện đến hạn; `student_cancel(...)`: xử lý sinh viên chủ động hủy; `verify(...)`: tra cứu và xác minh bảng điểm đã ký.
- `check_grades(...)` (khoảng dòng 531) áp dụng luật đối chiếu như D0–D7, cảnh báo A1 và ghi chú I1.
- `compare_grade_sources(...)` so khớp điểm đang vận hành với các nguồn tham chiếu theo MSSV, năm học, học kỳ và mã học phần; báo dòng thiếu, dòng thừa và trường dữ liệu lệch.
- `grade_review_assistance(...)` tổng hợp luật D0–D7/A1/I1, sai khác từ nguồn tham chiếu, các nguyên nhân khả dĩ theo mẫu và bản nháp ghi chú. Các hàm này chỉ tạo kết quả; không nhận đối tượng database và không sửa điểm.

### Tính năng hỗ trợ Khoa rà soát điểm

Luồng của tính năng được nối qua ba lớp:

1. **Dữ liệu so sánh:** `bangdiem/schema.sql` khai báo `grade_reference_sources` và `grade_reference_grades`; `bangdiem/store.py` nạp nguồn vào bộ nhớ nhưng không ghi đè chúng trong các giao dịch thông thường. Lần đầu hệ thống tạo một bộ tham chiếu demo tách biệt. PĐT có thể thay nguồn qua `POST /api/admin/reference-grades`.
2. **Phân tích:** `bangdiem/engine.py`, `compare_grade_sources(...)` so sánh các trường; `grade_review_assistance(...)` gắn mã luật, giả thuyết nguyên nhân và nháp ghi chú. Kết quả đánh dấu `readOnly: True` và `humanDecisionRequired: True`.
3. **Kiểm soát quyền và cung cấp dữ liệu:** `app.py`, route chi tiết yêu cầu chỉ thêm kết quả cho Khoa khi yêu cầu ở trạng thái `CHO_KHOA`.
4. **Hiển thị và nhập nguồn:** `static/js/app.js`, hàm `khoaBox(...)`, hiển thị sai khác, nguyên nhân dự kiến và bản nháp để cán bộ chỉnh sửa. Khu vực **Hệ thống & dữ liệu › CSDL điểm** cho phép PĐT nạp CSV riêng làm nguồn tham chiếu. `static/css/style.css` định dạng thẻ `.grade-assistant`.

Đây là phân tích xác định theo luật cục bộ, **không phải mô hình LLM và không gửi dữ liệu ra dịch vụ AI**. Bộ nguồn mặc định là dữ liệu tổng hợp demo, không phải dữ liệu chính thức; chỉ nguồn tham chiếu do đơn vị có thẩm quyền cung cấp mới có thể làm căn cứ nghiệp vụ. Nguyên nhân hiển thị chỉ là giả thuyết; Khoa phải tự xác minh và quyết định. Tính năng không tự thay đổi dữ liệu.

### `bangdiem/store.py` — lớp lưu trữ

- `Store` khởi tạo và mở kết nối SQLite hoặc Turso tùy cấu hình.
- Nạp dữ liệu từ các bảng thành đối tượng `Db` của engine; lưu các thay đổi trở lại CSDL.
- Quản lý phiên đọc/ghi, giao dịch, khóa ghi và chuyển đổi các trường JSON.
- Các hàm cuối module đọc/tìm/tạo/cập nhật tài khoản người dùng.

### `bangdiem/schema.sql` — lược đồ CSDL

Khai báo bảng và chỉ mục: tài khoản, sinh viên, điểm vận hành, nguồn điểm tham chiếu, yêu cầu, lịch sử BPMN, email, nhật ký kiểm toán, bảng điểm đã ký, sổ cấp phát, cấu hình hệ thống. `grade_reference_sources` quản lý tên/loại nguồn; `grade_reference_grades` lưu các dòng tham chiếu riêng, không dùng chung bảng `grades`.

### `bangdiem/bpmn.py` — danh mục BPMN dùng trong ứng dụng

- `LANES`, `STEPS`: ánh xạ mã phần tử BPMN sang tên, vai trò và loại bước.
- `STATUS`: ánh xạ trạng thái yêu cầu sang bước hiện tại, vai trò xử lý và kiểu hiển thị.
- `CANCELLABLE`: danh sách trạng thái còn cho phép sinh viên chủ động hủy.
- `parse_flows(...)`: đọc các `sequenceFlow` trong tệp BPMN để giao diện hiển thị đường đi.
- `catalog()`: cung cấp danh mục BPMN cho frontend.

### `bangdiem/signing.py` — ký và xác minh chữ ký

Lớp `Signer` dùng RSA-PSS/SHA-256 để ký hash của nội dung bảng điểm chuẩn hóa và kiểm tra chữ ký. Khóa riêng được nạp từ cấu hình môi trường hoặc tệp khóa runtime; khóa công khai được dùng để xác minh. Không đưa khóa riêng hoặc passphrase thật vào tài liệu, Git hay mã nguồn.

### `bangdiem/mailer.py` — email hệ thống

`Mailer` lưu email vào hộp thư nội bộ; nếu có cấu hình SMTP thì gửi email nền. Có tùy chọn chuyển hướng email khi demo. Kết quả gửi được ghi nhận để không làm gián đoạn tiến trình nghiệp vụ.

### `bangdiem/csvio.py` — nhập/xuất CSV và JSON

- Chuẩn hóa tiêu đề cột tiếng Việt có dấu và các tên cột tương đương.
- `parse_any(...)` đọc danh sách JSON hoặc CSV phân tách bằng dấu phẩy, chấm phẩy hay tab.
- `to_csv(...)` xuất các dòng dữ liệu ra CSV.
- Lỗi định dạng đầu vào được trả về dưới dạng lỗi nghiệp vụ.

### `bangdiem/seed.py` — dữ liệu mẫu

Khai báo sinh viên, học phần và kịch bản demo hư cấu; tạo dữ liệu điểm xác định/lặp lại được để phục vụ demo và kiểm thử. Các hàm nạp dữ liệu mẫu không đại diện cho dữ liệu học tập thật.

### `bangdiem/__init__.py`

Đánh dấu thư mục `bangdiem` là Python package; các module được import theo tên package này.

## 3. Frontend

### `static/index.html`

Khung trang HTML ban đầu: tiêu đề, thanh điều hướng, vùng nội dung, vùng thông báo, tìm kiếm yêu cầu/mã xác thực và phần chân trang. File nạp `css/style.css` và `js/app.js`.

### `static/js/app.js`

Ứng dụng giao diện phía trình duyệt:

- Gọi API, quản lý trạng thái đăng nhập và cập nhật màn hình theo vai trò.
- Hiển thị danh sách/chi tiết yêu cầu và biểu mẫu cho các bước nghiệp vụ.
- `khoaBox(...)` hiển thị bảng điểm, cảnh báo đối chiếu và phần gợi ý rà soát Khoa.
- Xử lý thao tác giao diện như đăng nhập, gửi yêu cầu, bổ sung, phê duyệt, tìm kiếm và chế độ sáng/tối.

### `static/css/style.css`

Khai báo màu sắc, bố cục, thành phần giao diện, trạng thái yêu cầu và hiển thị tương thích màn hình nhỏ. Các quy tắc `.grade-assistant` định dạng thẻ gợi ý rà soát.

### `static/assets/logo-due.png`, `static/bpmn/to-be.svg`

Tài nguyên tĩnh: hình logo được giao diện sử dụng và sơ đồ BPMN SVG phục vụ hiển thị.

## 4. Kiểm thử

### `tests/test_quy_trinh.py`

Kiểm thử trực tiếp bộ máy nghiệp vụ: luồng cấp bảng điểm chính, xác thực/bổ sung, ngoại lệ dữ liệu, xử lý của Khoa, kiểm tra/phê duyệt, ký số, tính điểm và các nhánh BPMN. Có kiểm thử gợi ý rà soát theo luật và xác nhận dữ liệu đầu vào không bị thay đổi.

### `tests/test_api.py`

Kiểm thử Flask API bằng test client: đăng nhập, quyền theo vai trò, CSRF, quy trình qua API, lưu bền vững và tra cứu chữ ký. Có kiểm thử chỉ Khoa được nhận `reviewAssistant` ở trạng thái phù hợp.

### `tests/test_turso_store.py`

Kiểm thử lớp lưu trữ và hành vi kết nối Turso/SQLite, bao gồm giao dịch, thao tác đọc/ghi, xử lý dữ liệu truy vấn và cấu hình triển khai liên quan.

Chạy toàn bộ kiểm thử từ thư mục gốc:

```powershell
python -m unittest discover -s tests -v
```

## 5. Cấu hình, triển khai và tiện ích

| Tệp/thư mục | Chức năng |
|---|---|
| `api/index.py` | Gọi `create_app()` và xuất biến `app` cho nền tảng triển khai serverless. |
| `vercel.json` | Khai báo build Python, route toàn bộ request tới entrypoint API và vùng triển khai. |
| `requirements.txt` | Khai báo Flask, thư viện ký số `cryptography` và driver Turso. |
| `.env.example` | Mẫu tên biến cấu hình; dùng để biết cấu hình cần thiết, không chứa giá trị bí mật thật. |
| `.gitignore` | Quy định các tệp runtime, môi trường cục bộ hoặc bí mật không nên đưa vào Git. |
| `chay.bat`, `chay.sh` | Tạo môi trường Python nếu cần, cài dependencies và chạy ứng dụng cục bộ trên Windows hoặc shell Unix. |
| `tools/xuat_du_lieu_mau.py` | Sinh CSV mẫu sinh viên, điểm và yêu cầu từ dữ liệu trong `seed.py`. |

## 6. Dữ liệu, sơ đồ và tài liệu

| Tệp/thư mục | Chức năng |
|---|---|
| `bpmn/BPMN_TO_BE_NHOM5_da_sua.bpmn` | Mô hình BPMN quy trình TO-BE; mã bước được ánh xạ trong `bangdiem/bpmn.py`. |
| `bpmn/diagram.svg` | Sơ đồ SVG đi cùng mô hình BPMN. |
| `data/mau-sinh-vien.csv`, `data/mau-diem.csv`, `data/mau-yeu-cau.csv` | Các tệp CSV mẫu dùng thử nhập dữ liệu. |
| `data/demo-sinh-vien-bo-sung.csv`, `data/demo-diem-bo-sung.csv` | Dữ liệu demo bổ sung. Đây là dữ liệu hư cấu, không dùng làm điểm thật. |
| `grade_reference_sources`, `grade_reference_grades` trong CSDL | Nguồn tham chiếu được lưu riêng; nguồn DEMO khởi tạo tự động, có thể thay bằng CSV được phê duyệt qua giao diện PĐT. |
| `data/bangdiem.db` | CSDL SQLite runtime cục bộ; có thể được tạo/cập nhật khi chạy ứng dụng. Không nên coi đây là mã nguồn hay dữ liệu phù hợp để công khai. |
| `docs/thiet-ke.md` | Thiết kế phần mềm, mô hình dữ liệu và ánh xạ quy trình. |
| `docs/test-case.md` | Danh mục test case nghiệp vụ, ngoại lệ, API và hạ tầng. |
| `docs/Bo_kiem_thu_test_case_cap_bang_diem.docx` | Bản Word bộ kiểm thử. |
| `docs/Gtmaxacthuc.md` | Giải thích mã xác thực và mục đích tra cứu bảng điểm đã ký. |
| `docs/chitiet.md` | Tài liệu hiện tại: hướng dẫn cấu trúc file và các đoạn code chính. |

## 7. Khởi chạy và kiểm tra nhanh

1. Cài Python và các gói được khai báo trong `requirements.txt`.
2. Chạy `chay.bat` trên Windows hoặc `chay.sh` trên môi trường shell; có thể chạy `python app.py` trực tiếp.
3. Mở `http://127.0.0.1:5000`.
4. Chạy `python -m unittest discover -s tests -v` để kiểm tra tự động.

Khi vận hành môi trường thật, cần cấu hình bí mật và cơ sở dữ liệu bền vững qua biến môi trường/secret manager phù hợp. Không công khai khóa riêng, mật khẩu, token hoặc dữ liệu cá nhân trong tài liệu hay repository.
