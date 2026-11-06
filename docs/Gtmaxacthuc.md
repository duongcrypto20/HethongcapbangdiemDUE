(tại sao phải tra cứu bằng mã xác thực, tra cứu bằng mã số sinh viên (mssv) không được à)
Không bắt buộc phải tra cứu bằng mã xác thực; hệ thống hiện chọn cách này để đơn vị nhận bảng điểm kiểm tra một bản bảng điểm cụ thể: mã giúp tìm đúng bản đã ký, rồi hệ thống kiểm tra nội dung và chữ ký số có bị sửa hay không.

Tra cứu công khai chỉ bằng MSSV có thể làm lộ việc một người có yêu cầu cấp bảng điểm, hoặc thông tin học tập nếu hệ thống trả về dữ liệu. MSSV cũng thường dễ đoán hơn mã xác thực. Vì vậy, không nên cho tra cứu công khai chỉ bằng MSSV.

Có thể thiết kế tra cứu theo MSSV nếu có bước bảo vệ, chẳng hạn đăng nhập tài khoản sinh viên hoặc MSSV kèm mã xác thực. Cách sau vừa tìm được bảng điểm vừa giữ bước kiểm chứng chữ ký; mã xác thực vẫn cần để xác nhận bản bảng điểm là nguyên vẹn.

(ưu điểm của tra cứu bằng mã Xác thực, sinh viên chỉ có mssv thì sao mà sinh viên biết được mã xác thực để mà tra cứu)
Sinh viên không cần có mã xác thực từ đầu. Mã chỉ được tạo sau khi bảng điểm hoàn tất phê duyệt và ký số. Khi đó, mã được ghi trên bảng điểm và thông báo cấp bảng điểm; sinh viên đăng nhập có thể xem mã ở chi tiết yêu cầu. Cách này được triển khai tại sign_and_dispatch và giao diện chi tiết tại app.js.

Mục Tra cứu dành chủ yếu cho bên nhận bảng điểm—ví dụ nơi tiếp nhận hồ sơ—để nhập mã in trên bảng điểm và kiểm tra chữ ký, phát hiện nội dung bị sửa. Nếu sinh viên chỉ có MSSV và chưa được cấp bảng điểm thì chưa có mã để tra; họ cần đăng nhập, gửi yêu cầu và chờ bảng điểm được ký.

Một điểm cần cải thiện: email thật chỉ được gửi nếu hệ thống cấu hình SMTP; nếu không, thông báo nằm trong hộp thư nội bộ. Vì vậy nên hướng dẫn sinh viên xem mã trong chi tiết yêu cầu/hộp thư của hệ thống, thay vì chỉ nói email.