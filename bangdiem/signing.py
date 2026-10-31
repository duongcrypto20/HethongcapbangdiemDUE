"""Ký số bảng điểm bằng RSA-PSS (SHA-256) với thư viện ``cryptography``.

- Khóa bí mật lưu ở ``keys/signing_key.pem``, **được mã hóa** bằng passphrase lấy từ biến
  môi trường ``SIGN_KEY_PASSPHRASE`` (không ghi passphrase vào mã nguồn hay CSDL).
- Thư mục ``keys/`` nằm trong ``.gitignore``; chỉ khóa công khai được phát hành
  (``GET /api/public-key``) để bên thứ ba tự kiểm chứng.
- Chữ ký được tạo trên giá trị băm SHA-256 của nội dung bảng điểm dạng JSON chuẩn hóa.
"""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

DEV_PASSPHRASE = "doi-passphrase-nay-khi-trien-khai"


class Signer:
    algorithm = "RSA-PSS-SHA256"

    def __init__(self, key_dir: str | Path, passphrase: str | None = None):
        self.key_dir = Path(key_dir)
        self.passphrase = (passphrase or os.environ.get("SIGN_KEY_PASSPHRASE") or DEV_PASSPHRASE).encode()
        self.using_dev_passphrase = self.passphrase == DEV_PASSPHRASE.encode()
        self.key_path = self.key_dir / "signing_key.pem"
        self.pub_path = self.key_dir / "signing_key.pub.pem"
        self._key = self._load_or_create()
        self._pub = self._key.public_key()
        der = self._pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.key_id = hashlib.sha256(der).hexdigest()[:16].upper()

    def _load_or_create(self):
        if self.key_path.exists():
            return serialization.load_pem_private_key(self.key_path.read_bytes(), password=self.passphrase)
        self.key_dir.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(self.passphrase),
        )
        self.key_path.write_bytes(pem)
        try:
            os.chmod(self.key_path, 0o600)  # chỉ tài khoản chạy ứng dụng được đọc
        except OSError:
            pass
        self.pub_path.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        return key

    def sign(self, hash_hex: str) -> str:
        sig = self._key.sign(
            hash_hex.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    def verify(self, hash_hex: str, signature_b64: str) -> bool:
        try:
            self._pub.verify(
                base64.b64decode(signature_b64),
                hash_hex.encode(),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    def public_pem(self) -> str:
        return self._pub.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
