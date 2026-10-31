"""Dịch vụ email (tích hợp bên ngoài).

Mọi email đều được lưu vào bảng ``emails`` (hộp thư mô phỏng) để xem lại trên web.
Nếu đặt biến môi trường ``SMTP_HOST`` thì email còn được gửi thật qua SMTP
(ví dụ Gmail: smtp.gmail.com, cổng 587, mật khẩu ứng dụng). Gửi lỗi không làm dừng quy trình:
trạng thái gửi được ghi vào trường ``delivery`` để Phòng Đào tạo theo dõi.
"""
from __future__ import annotations

import os
import smtplib
import threading
from email.message import EmailMessage


class Mailer:
    def __init__(self):
        self.host = os.environ.get("SMTP_HOST", "").strip()
        self.port = int(os.environ.get("SMTP_PORT", "587") or 587)
        self.user = os.environ.get("SMTP_USER", "").strip()
        self.password = os.environ.get("SMTP_PASSWORD", "")
        self.sender = os.environ.get("SMTP_FROM", self.user or "no-reply@example.com")
        # Chế độ an toàn khi demo: chỉ gửi tới địa chỉ này thay vì email thật của SV
        self.redirect_to = os.environ.get("SMTP_REDIRECT_TO", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.host)

    def __call__(self, mail: dict) -> None:
        """Được engine gọi mỗi khi tạo email; gửi nền để không chặn thao tác của người dùng."""
        if not self.enabled:
            return
        mail["delivery"] = "smtp-queued"
        threading.Thread(target=self._send, args=(dict(mail),), daemon=True).start()

    def _send(self, mail: dict) -> None:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = self.redirect_to or mail["to"]
        msg["Subject"] = mail["subject"]
        msg.set_content(mail["body"] + (f"\n\n(Gửi chuyển hướng, người nhận gốc: {mail['to']})" if self.redirect_to else ""))
        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as s:
                s.starttls()
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)
        except Exception as exc:  # noqa: BLE001 — chỉ ghi nhận, không làm hỏng quy trình
            print(f"[mailer] Gửi email {mail.get('id')} thất bại: {exc}")
