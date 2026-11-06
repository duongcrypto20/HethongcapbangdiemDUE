BỘ KIỂM THỬ
QUY TRÌNH CẤP BẢNG ĐIỂM
Test case nghiệp vụ, ngoại lệ, API và hạ tầng
Hệ thống xét duyệt và cấp phát bảng điểm (TO-BE)
Ngày lập: 06/11/2026

Tổng số test case	46
Nghiệp vụ/quy trình	24 (TC01-TC23, TC45)
API/xác thực	12 (TC24-TC34, TC46)
Lưu trữ/triển khai/ký số	10 (TC35-TC44)
Tự động hóa	Python unittest; bao gồm 6 test nghiệp vụ bổ sung mới

1. Mục tiêu và cách sử dụng
Tài liệu mô tả luồng chính, nhánh nghiệp vụ, tình huống ngoại lệ và kiểm tra API/hạ tầng của quy trình cấp bảng điểm.
Tiền điều kiện chung: cài Python 3.10+ và các thư viện trong requirements.txt; chạy lệnh kiểm thử tại thư mục gốc repository.
Lệnh chạy: python -m unittest discover -s tests -v
Mã kết quả: “Có - unittest” nghĩa là có kiểm thử tự động tương ứng. Các bước mô tả là kịch bản nghiệp vụ/đầu vào; kiểm thử tự động dùng dữ liệu cố định và CSDL tạm để không sửa dữ liệu demo.
Vai trò: SV = Sinh viên; Khoa = Văn phòng Khoa; PĐT = Phòng Đào tạo; Phó phòng = người phê duyệt. Ngưỡng bản giấy hiện tại lấy từ cấu hình hệ thống (mặc định tối đa 10).
2. Danh sách test case
TC01 - Cấp bảng điểm điện tử thành công
Nhóm	Luồng chính
Loại	Nghiệp vụ
Tiền điều kiện	Sinh viên có hồ sơ/điểm hợp lệ; đăng nhập đúng vai trò.
Các bước / dữ liệu	SV gửi yêu cầu → PĐT xác nhận đạt → Phó phòng phê duyệt.
Kết quả mong đợi	Yêu cầu HOAN_TAT; bảng điểm được ký số, email thông báo được gửi và sổ cấp phát có 1 bản ghi.
Tự động hóa	Có - unittest

TC02 - Bổ sung thông tin sai rồi gửi lại
Nhóm	Xác thực đầu vào
Loại	Nghiệp vụ
Tiền điều kiện	Hồ sơ SV tồn tại; biểu mẫu ban đầu có ngày sinh sai.
Các bước / dữ liệu	Gửi yêu cầu → kiểm tra email yêu cầu bổ sung → SV cập nhật ngày sinh đúng và gửi lại.
Kết quả mong đợi	Lần đầu CHO_BO_SUNG; sau bổ sung hệ thống xác thực lại, tăng số lần thử và tiếp tục quy trình nếu hợp lệ.
Tự động hóa	Có - unittest

TC03 - Tự hủy khi quá hạn bổ sung
Nhóm	Ngoại lệ - timer
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đang CHO_BO_SUNG.
Các bước / dữ liệu	Tua đồng hồ đến trước hạn 3 ngày, kiểm tra trạng thái; tua qua hạn và kiểm tra lại.
Kết quả mong đợi	Chưa đến hạn không hủy; quá hạn chuyển DA_HUY, gửi thông báo và ghi nhật ký cảnh báo.
Tự động hóa	Có - unittest

TC04 - Khoa hiệu chỉnh điểm còn thiếu
Nhóm	Ngoại lệ - dữ liệu điểm
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu qua xác thực; một dòng điểm thiếu điểm (D1).
Các bước / dữ liệu	Mở rà soát Khoa → nhập điểm hợp lệ → yêu cầu đối chiếu lại.
Kết quả mong đợi	Có audit log; yêu cầu rời CHO_KHOA và tiếp tục sang bước phù hợp sau khi điểm đạt kiểm tra.
Tự động hóa	Có - unittest

TC05 - Khoa từ chối khi không thể hiệu chỉnh
Nhóm	Ngoại lệ - nghiệp vụ
Loại	Nghiệp vụ
Tiền điều kiện	SV không có học kỳ/điểm trong CSDL (D0).
Các bước / dữ liệu	Khoa chọn không thể hiệu chỉnh và nhập lý do.
Kết quả mong đợi	Yêu cầu KHOA_TU_CHOI; lưu lý do, gửi thông báo và không tạo bảng điểm để ký.
Tự động hóa	Có - unittest

TC06 - Nhắc Khoa khi quá hạn xử lý
Nhóm	Timer / thông báo
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đang chờ Khoa và dữ liệu cần rà soát.
Các bước / dữ liệu	Tua đồng hồ qua ngưỡng 2 ngày; tiếp tục tua thêm nhiều ngày.
Kết quả mong đợi	Có email nhắc đúng một lần; yêu cầu vẫn CHO_KHOA, không tự chuyển trạng thái.
Tự động hóa	Có - unittest

TC07 - Khoa xác nhận điểm bất thường
Nhóm	Ngoại lệ - điểm bất thường
Loại	Nghiệp vụ
Tiền điều kiện	Dữ liệu điểm có cảnh báo A1; độ tin cậy dưới ngưỡng.
Các bước / dữ liệu	Khoa xác nhận cảnh báo là đúng thực tế → chấp thuận xử lý.
Kết quả mong đợi	Cảnh báo được xác nhận, độ tin cậy được cập nhật và luồng tiếp tục khi không còn lỗi chặn.
Tự động hóa	Có - unittest

TC08 - PĐT yêu cầu chỉnh sửa bảng điểm
Nhóm	Luồng sửa lỗi
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đang CHO_KIEM_TRA.
Các bước / dữ liệu	PĐT chọn chưa đạt nhưng có góp ý → cập nhật bản điểm (ví dụ ngôn ngữ) → kiểm tra lại.
Kết quả mong đợi	Thiếu góp ý bị từ chối; có góp ý chuyển CHO_CHINH_SUA; tạo phiên bản mới và quay lại kiểm tra.
Tự động hóa	Có - unittest

TC09 - Phó phòng yêu cầu sửa rồi phê duyệt
Nhóm	Luồng sửa lỗi
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đã qua kiểm tra PĐT, đang chờ phê duyệt.
Các bước / dữ liệu	Phó phòng yêu cầu sửa có ghi chú → PĐT chỉnh sửa → kiểm tra đạt → Phó phòng phê duyệt.
Kết quả mong đợi	Lưu phản hồi; tạo phiên bản mới; sau phê duyệt hoàn tất và ký số.
Tự động hóa	Có - unittest

TC10 - Phó phòng từ chối và bắt buộc có lý do
Nhóm	Ngoại lệ - phê duyệt
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đang CHO_PHE_DUYET.
Các bước / dữ liệu	Thử từ chối không lý do → gửi lại quyết định từ chối kèm lý do.
Kết quả mong đợi	Thiếu lý do phát sinh lỗi nghiệp vụ; từ chối hợp lệ chuyển PP_TU_CHOI và không ký số.
Tự động hóa	Có - unittest

TC11 - Nhắc Phó phòng quá hạn
Nhóm	Timer / thông báo
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đang CHO_PHE_DUYET.
Các bước / dữ liệu	Tua đến trước 24 giờ, xác nhận chưa nhắc → tua qua hạn.
Kết quả mong đợi	Chỉ gửi nhắc sau ngưỡng 1 ngày; yêu cầu vẫn chờ phê duyệt.
Tự động hóa	Có - unittest

TC12 - Cấp đồng thời bản điện tử và bản giấy
Nhóm	Cổng bao hàm
Loại	Nghiệp vụ
Tiền điều kiện	Biểu mẫu yêu cầu 2 bản giấy; dữ liệu điểm hợp lệ.
Các bước / dữ liệu	PĐT kiểm tra → Phó phòng phê duyệt → in → đóng dấu → xác nhận người nhận.
Kết quả mong đợi	Chỉ hoàn thành nhánh giấy thì mới hoàn tất; ghi nhận đủ 2 bản giấy vào sổ cấp phát.
Tự động hóa	Có - unittest

TC13 - Chuẩn hóa họ tên khi đối chiếu
Nhóm	Kiểm tra biên
Loại	Nghiệp vụ
Tiền điều kiện	Hồ sơ SV tồn tại.
Các bước / dữ liệu	Đối chiếu đúng tên không dấu/khác khoảng trắng; thử thêm tên sai khác đáng kể.
Kết quả mong đợi	Tên tương đương được chấp nhận; tên sai dưới ngưỡng bị đánh dấu không hợp lệ để bổ sung.
Tự động hóa	Có - unittest

TC14 - Xác minh chữ ký và phát hiện nội dung bị sửa
Nhóm	Ngoại lệ - toàn vẹn
Loại	Nghiệp vụ
Tiền điều kiện	Có bảng điểm đã ký số.
Các bước / dữ liệu	Xác minh mã đúng → sửa nội dung đã lưu → xác minh lại → thử mã không tồn tại và chữ ký giả.
Kết quả mong đợi	Mã hợp lệ ban đầu pass; dữ liệu/chữ ký bị sửa không hợp lệ; mã lạ trả không tìm thấy.
Tự động hóa	Có - unittest

TC15 - Tính GPA khi học lại và tích lũy tín chỉ
Nhóm	Quy tắc tính điểm
Loại	Nghiệp vụ
Tiền điều kiện	Có các môn đạt, trượt và học lại.
Các bước / dữ liệu	Tính tổng kết trên dữ liệu mẫu có môn học lại.
Kết quả mong đợi	Lấy điểm cao nhất của môn học lại; tín chỉ tích lũy chỉ tính môn đạt; GPA khớp kết quả kiểm thử 1.94 và 5 tín chỉ.
Tự động hóa	Có - unittest

TC16 - Lỗi truy xuất CSDL điểm và gửi lại
Nhóm	Ngoại lệ - hệ thống
Loại	Nghiệp vụ
Tiền điều kiện	Bật giả lập sự cố truy xuất CSDL điểm.
Các bước / dữ liệu	SV gửi yêu cầu khi lỗi đang bật → tắt lỗi → gửi yêu cầu mới.
Kết quả mong đợi	Lần đầu LOI_HE_THONG, có log lỗi/email và không chạy đối chiếu; sau khôi phục yêu cầu mới tiếp tục bình thường.
Tự động hóa	Có - unittest

TC17 - SV chủ động hủy trước khi ký số
Nhóm	Ngoại lệ - hủy
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đang chờ Phó phòng, chưa ký số.
Các bước / dữ liệu	SV gửi yêu cầu hủy kèm lý do → tua thời gian qua hạn nhắc.
Kết quả mong đợi	Yêu cầu chuyển SV_HUY, dừng timer và không tiếp tục xử lý/nhắc; quyết định phê duyệt sau đó bị chặn.
Tự động hóa	Có - unittest

TC18 - Chặn hủy sau khi đã ký số
Nhóm	Ngoại lệ - trạng thái
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu đã ký số, đang chờ xử lý bản giấy.
Các bước / dữ liệu	SV gửi yêu cầu hủy.
Kết quả mong đợi	Hệ thống từ chối thao tác; yêu cầu giữ trạng thái và chữ ký hiện có.
Tự động hóa	Có - unittest

TC19 - Nạp và chạy các kịch bản dữ liệu mẫu
Nhóm	Hồi quy dữ liệu mẫu
Loại	Nghiệp vụ
Tiền điều kiện	CSDL mẫu được khởi tạo.
Các bước / dữ liệu	Chạy hàm nạp dữ liệu/kịch bản mẫu; kiểm tra trạng thái yêu cầu và hộp thư.
Kết quả mong đợi	Các yêu cầu mẫu ở đúng trạng thái thiết kế; timer nhắc Khoa được kích hoạt theo dữ liệu mẫu.
Tự động hóa	Có - unittest

TC20 - MSSV không tồn tại
Nhóm	Ngoại lệ - X1/X4
Loại	Nghiệp vụ
Tiền điều kiện	Không có sinh viên với MSSV nhập thử.
Các bước / dữ liệu	Gửi yêu cầu bằng MSSV lạ, email hợp lệ định dạng nhưng không thuộc hồ sơ.
Kết quả mong đợi	Chuyển CHO_BO_SUNG; X1 và X4 thất bại; gửi thông báo bổ sung, không truy xuất điểm.
Tự động hóa	Có - unittest

TC21 - Ngày sinh/email/điện thoại/mục đích/trạng thái sai
Nhóm	Ngoại lệ - X3-X7
Loại	Nghiệp vụ
Tiền điều kiện	Hồ sơ có trạng thái đã xóa tên.
Các bước / dữ liệu	Gửi dữ liệu ngày sinh sai, email sai định dạng, điện thoại không đủ 10 số, mục đích dưới 5 ký tự.
Kết quả mong đợi	Các luật X3, X4, X5, X6, X7 được báo lỗi tương ứng; yêu cầu không vượt qua xác thực.
Tự động hóa	Có - unittest

TC22 - Biên số bản giấy
Nhóm	Giá trị biên - X8
Loại	Nghiệp vụ
Tiền điều kiện	SV tồn tại; bật tùy chọn bản giấy.
Các bước / dữ liệu	Thử số bản 1, 10; sau đó thử 0, 11 và boolean.
Kết quả mong đợi	1 và 10 hợp lệ (theo cấu hình hiện tại); 0, 11 và kiểu boolean bị từ chối theo luật X8.
Tự động hóa	Có - unittest

TC23 - Điểm ngoài thang, điểm chữ sai, tín chỉ sai, thiếu mã HP
Nhóm	Ngoại lệ - D2/D3/D4/D7
Loại	Nghiệp vụ
Tiền điều kiện	Yêu cầu có các dòng điểm cần kiểm tra.
Các bước / dữ liệu	Đưa điểm 10.1, điểm chữ không tương ứng, tín chỉ 0 và thiếu mã học phần; gửi yêu cầu.
Kết quả mong đợi	Các lỗi D2, D3, D4, D7 xuất hiện; yêu cầu chuyển CHO_KHOA để rà soát.
Tự động hóa	Có - unittest

TC24 - Đăng nhập sai mật khẩu
Nhóm	API / xác thực
Loại	Nghiệp vụ
Tiền điều kiện	Chưa đăng nhập.
Các bước / dữ liệu	Gọi POST /api/login với mật khẩu sai → truy cập /api/state.
Kết quả mong đợi	Đăng nhập HTTP 401; truy cập dữ liệu khi chưa đăng nhập HTTP 401.
Tự động hóa	Có - unittest

TC25 - Đăng nhập SV bằng họ tên hoặc MSSV
Nhóm	API / xác thực
Loại	Nghiệp vụ
Tiền điều kiện	Bật DEMO_MODE; có tài khoản mẫu.
Các bước / dữ liệu	Đăng nhập lần lượt bằng họ tên (không phân biệt hoa thường/khoảng trắng) và MSSV với mật khẩu đúng; thử mật khẩu sai.
Kết quả mong đợi	Tài khoản hợp lệ được đăng nhập; mật khẩu sai HTTP 401; thông tin demo chỉ hiển thị ở chế độ demo.
Tự động hóa	Có - unittest

TC26 - Khóa tạm sau 5 lần đăng nhập sai
Nhóm	API / chống thử mật khẩu
Loại	Nghiệp vụ
Tiền điều kiện	Chưa vượt ngưỡng đăng nhập sai cho tài khoản.
Các bước / dữ liệu	Gửi 5 lần đăng nhập sai liên tiếp → thử mật khẩu đúng ngay sau đó.
Kết quả mong đợi	Lần thử tiếp theo bị giới hạn HTTP 429 trong thời gian khóa.
Tự động hóa	Có - unittest

TC27 - Phân quyền theo vai trò và phạm vi dữ liệu
Nhóm	API / phân quyền
Loại	Nghiệp vụ
Tiền điều kiện	Có tài khoản SV, Khoa và PĐT; yêu cầu thuộc Khoa xác định.
Các bước / dữ liệu	SV thử gọi tác vụ PĐT/xem yêu cầu người khác; Khoa xem yêu cầu ngoài Khoa.
Kết quả mong đợi	Thao tác sai vai trò hoặc ngoài phạm vi bị HTTP 403; SV chỉ thấy yêu cầu của mình, Khoa chỉ thấy dữ liệu đơn vị.
Tự động hóa	Có - unittest

TC28 - Bắt buộc CSRF với thao tác ghi
Nhóm	API / CSRF
Loại	Nghiệp vụ
Tiền điều kiện	SV đã đăng nhập và có cookie phiên.
Các bước / dữ liệu	Gọi POST tạo yêu cầu nhưng không có X-CSRF-Token.
Kết quả mong đợi	API trả HTTP 403; không tạo yêu cầu mới.
Tự động hóa	Có - unittest

TC29 - Luồng API đầy đủ và lưu bền vững
Nhóm	API / tích hợp
Loại	Nghiệp vụ
Tiền điều kiện	CSDL SQLite test; các vai trò được tạo sẵn.
Các bước / dữ liệu	SV tạo yêu cầu → PĐT thử quyết định thiếu góp ý rồi quyết định hợp lệ → thử lặp sai bước → Phó phòng duyệt → khởi động lại app và xác minh mã.
Kết quả mong đợi	Thiếu góp ý HTTP 400; xử lý đúng thành công; lặp sai bước HTTP 409; trạng thái/chữ ký còn sau khởi động lại và xác minh hợp lệ.
Tự động hóa	Có - unittest

TC30 - SV hủy yêu cầu qua API
Nhóm	API / ngoại lệ
Loại	Nghiệp vụ
Tiền điều kiện	SV sở hữu yêu cầu đang ở trạng thái cho phép hủy.
Các bước / dữ liệu	Gọi POST /api/requests/{id}/cancel kèm lý do và CSRF.
Kết quả mong đợi	API thành công; trạng thái yêu cầu thành SV_HUY.
Tự động hóa	Có - unittest

TC31 - Sự cố truy xuất điểm qua API
Nhóm	API / ngoại lệ
Loại	Nghiệp vụ
Tiền điều kiện	PĐT đăng nhập và có quyền bật giả lập lỗi.
Các bước / dữ liệu	PĐT bật sự cố → SV gửi yêu cầu.
Kết quả mong đợi	Yêu cầu phản ánh LOI_HE_THONG; không trả kết quả cấp bảng điểm thành công giả.
Tự động hóa	Có - unittest

TC32 - Nhập CSV tạo hồ sơ và tài khoản SV
Nhóm	API / dữ liệu
Loại	Nghiệp vụ
Tiền điều kiện	PĐT đăng nhập; CSV có tiêu đề hợp lệ và một dòng SV mới.
Các bước / dữ liệu	POST nội dung CSV vào endpoint nhập sinh viên → đăng nhập bằng tài khoản vừa tạo.
Kết quả mong đợi	Kết quả thêm 1 hồ sơ; tài khoản SV được tạo và đăng nhập thành công.
Tự động hóa	Có - unittest

TC33 - Tua đồng hồ kích hoạt timer qua API
Nhóm	API / timer
Loại	Nghiệp vụ
Tiền điều kiện	PĐT đăng nhập; có timer bổ sung đang đến hạn.
Các bước / dữ liệu	POST /api/admin/clock với khoảng thời gian vượt hạn.
Kết quả mong đợi	Phản hồi liệt kê timer e_t3 đã kích hoạt; yêu cầu được cập nhật theo hạn.
Tự động hóa	Có - unittest

TC34 - Đăng nhập không thực hiện truy vấn người dùng lặp
Nhóm	API / hồi quy kỹ thuật
Loại	Nghiệp vụ
Tiền điều kiện	Dịch vụ xác thực hoạt động bình thường.
Các bước / dữ liệu	Theo dõi lời gọi get_user sau khi xác thực đăng nhập.
Kết quả mong đợi	Đăng nhập trả thông tin tài khoản/CSRF mà không gọi lại truy vấn CSDL không cần thiết.
Tự động hóa	Có - unittest

TC35 - Khóa giao dịch trước khi nạp snapshot ghi
Nhóm	Hồi quy hạ tầng
Loại	Nghiệp vụ
Tiền điều kiện	Dùng Store giả lập kết nối Turso.
Các bước / dữ liệu	Mở phiên ghi và ghi nhận thứ tự thao tác.
Kết quả mong đợi	Thứ tự: BEGIN IMMEDIATE → LOAD → xử lý → SAVE → COMMIT → CLOSE.
Tự động hóa	Có - unittest

TC36 - Phiên chỉ đọc không mở giao dịch ghi
Nhóm	Hồi quy hạ tầng
Loại	Nghiệp vụ
Tiền điều kiện	Dùng Store giả lập kết nối.
Các bước / dữ liệu	Mở phiên write=False và theo dõi lệnh SQL.
Kết quả mong đợi	Không BEGIN/COMMIT/SAVE; vẫn LOAD, xử lý đọc và CLOSE.
Tự động hóa	Có - unittest

TC37 - Cấu hình URL và token Turso theo cặp
Nhóm	Ngoại lệ cấu hình
Loại	Nghiệp vụ
Tiền điều kiện	Chỉ cấu hình URL hoặc chỉ cấu hình token.
Các bước / dữ liệu	Khởi tạo Store khi thiếu một trong hai tham số.
Kết quả mong đợi	Phát sinh ValueError nêu rõ yêu cầu cấu hình đồng thời; không kết nối sai cấu hình.
Tự động hóa	Có - unittest

TC38 - Kết nối Turso không tạo CSDL SQLite local
Nhóm	Hồi quy hạ tầng
Loại	Nghiệp vụ
Tiền điều kiện	Turso driver được giả lập; URL/token hợp lệ.
Các bước / dữ liệu	Khởi tạo Store remote và kiểm tra tham số/đường dẫn.
Kết quả mong đợi	Dùng Turso driver với token; không tạo thư mục/DB SQLite local cho kết nối remote.
Tự động hóa	Có - unittest

TC39 - Kết nối đọc remote bỏ qua vòng bật foreign key
Nhóm	Hồi quy hạ tầng
Loại	Nghiệp vụ
Tiền điều kiện	Store ở chế độ remote; kết nối đọc.
Các bước / dữ liệu	Gọi connect(foreign_keys=False) và theo dõi lệnh.
Kết quả mong đợi	Không gọi lệnh PRAGMA foreign_keys khi mở kết nối đọc remote.
Tự động hóa	Có - unittest

TC40 - Đọc nhiều truy vấn remote theo lô và giải mã hàng
Nhóm	Hồi quy hạ tầng
Loại	Nghiệp vụ
Tiền điều kiện	Turso trả về hàng dữ liệu kiểu integer/text.
Các bước / dữ liệu	Gọi fetchall nhiều truy vấn và kiểm tra pipeline/kết quả.
Kết quả mong đợi	Các truy vấn được gom pipeline; dữ liệu giải mã đúng kiểu và đúng tên cột.
Tự động hóa	Có - unittest

TC41 - Từ chối triển khai Vercel thiếu cấu hình bền vững
Nhóm	Ngoại lệ cấu hình
Loại	Nghiệp vụ
Tiền điều kiện	Môi trường VERCEL=1; thiếu TURSO_DATABASE_URL hoặc bí mật bắt buộc.
Các bước / dữ liệu	Khởi tạo ứng dụng với các biến môi trường chưa đủ.
Kết quả mong đợi	Khởi tạo thất bại rõ ràng với RuntimeError nếu biến cần thiếu, không chạy âm thầm trên SQLite tạm.
Tự động hóa	Có - unittest

TC42 - Entrypoint Vercel xuất Flask app
Nhóm	Hồi quy triển khai
Loại	Nghiệp vụ
Tiền điều kiện	Có module api/index.py.
Các bước / dữ liệu	Nạp entrypoint với create_app giả lập.
Kết quả mong đợi	create_app được gọi; biến app được xuất đúng đối tượng ứng dụng.
Tự động hóa	Có - unittest

TC43 - Nạp khóa ký ổn định từ biến môi trường
Nhóm	Hồi quy ký số
Loại	Nghiệp vụ
Tiền điều kiện	Có khóa ký được mã hóa Base64 hợp lệ.
Các bước / dữ liệu	Nạp Signer bằng SIGNING_PRIVATE_KEY_B64; ký và xác minh dữ liệu.
Kết quả mong đợi	Key ID trùng khóa gốc; xác minh chữ ký thành công; không cần tạo thư mục khóa local.
Tự động hóa	Có - unittest

TC44 - Từ chối khóa ký môi trường không hợp lệ
Nhóm	Ngoại lệ cấu hình
Loại	Nghiệp vụ
Tiền điều kiện	SIGNING_PRIVATE_KEY_B64 chứa dữ liệu không phải Base64/PEM hợp lệ.
Các bước / dữ liệu	Khởi tạo Signer.
Kết quả mong đợi	Phát sinh ValueError nếu SIGNING_PRIVATE_KEY_B64 không hợp lệ; không thay bằng khóa giả thành công.
Tự động hóa	Có - unittest

TC45 - Hỗ trợ Khoa rà soát điểm theo luật cục bộ, chỉ đọc
Nhóm	Rà soát điểm
Loại	Nghiệp vụ
Tiền điều kiện	Kết quả đối chiếu có lỗi D3, cảnh báo A1 và ghi chú I1.
Các bước / dữ liệu	Gọi hàm tạo gợi ý rà soát với kết quả kiểm tra; lưu lại dữ liệu đầu vào trước khi gọi.
Kết quả mong đợi	Tạo findings đúng mức độ và mã luật; đánh dấu phương pháp local-rules, readOnly và humanDecisionRequired; dữ liệu đầu vào không bị thay đổi. Gợi ý A1 nêu rõ đây chưa phải bằng chứng điểm sai và Khoa phải tự đối chiếu nguồn chính thức; công cụ không tự sửa dữ liệu.
Tự động hóa	Có - unittest

TC46 - Chỉ Khoa đang xử lý mới nhận gợi ý rà soát điểm
Nhóm	Phân quyền API
Loại	Ngoại lệ truy cập
Tiền điều kiện	Có yêu cầu thuộc quyền Khoa và đang ở trạng thái CHO_KHOA.
Các bước / dữ liệu	Khoa lấy chi tiết yêu cầu; sau đó Phòng Đào tạo lấy cùng chi tiết yêu cầu.
Kết quả mong đợi	API trả reviewAssistant cho Khoa với cờ chỉ đọc và cần quyết định của con người; response của Phòng Đào tạo không có trường reviewAssistant.
Tự động hóa	Có - unittest

3. Phạm vi kiểm thử tự động
Luồng BPMN: xác thực X1-X8, đối chiếu điểm D0-D7/A1, bổ sung, timer, nhánh Khoa, PĐT/Phó phòng, ký số, bản giấy và hủy.
API: đăng nhập, khóa đăng nhập, CSRF, phân quyền/phạm vi dữ liệu, tạo/hủy yêu cầu, CSV, timer, giả lập lỗi và lưu bền vững.
Hạ tầng: giao dịch Store/Turso, cấu hình triển khai Vercel và nạp/xác minh khóa ký.
Các test case mô tả kết quả mong đợi theo luật hiện có; việc kiểm thử chấp nhận trên môi trường triển khai thật cần chạy lại với dữ liệu và cấu hình được phê duyệt.