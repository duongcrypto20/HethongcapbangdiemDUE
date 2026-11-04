"""Lưu trữ bền vững trong SQLite hoặc Turso.

Mỗi phiên nạp trạng thái và ghi thay đổi trong một giao dịch. Giao dịch ghi lấy khóa
cơ sở dữ liệu trước khi đọc để các Vercel instance không cùng sửa một snapshot cũ.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from . import engine as E

SCHEMA = Path(__file__).with_name("schema.sql")

REQ_JSON = {  # cột JSON ↔ khóa trong đối tượng yêu cầu
    "form_json": "form", "options_json": "options", "validation_json": "validation", "check_json": "check",
    "acks_json": "acks", "transcript_json": "transcript", "auto_checks_json": "autoChecks", "feedback_json": "feedback",
    "signature_json": "signature", "timers_json": "timers", "paper_json": "paper", "branches_json": "branches",
    "student_snapshot_json": "studentSnapshot",
}
STUDENT_COLS = {"mssv": "mssv", "ho_ten": "hoTen", "ngay_sinh": "ngaySinh", "gioi_tinh": "gioiTinh", "lop": "lop",
                "khoa": "khoa", "nganh": "nganh", "khoa_hoc": "khoaHoc", "email": "email", "trang_thai": "trangThai"}
GRADE_COLS = {"id": "id", "mssv": "mssv", "nam_hoc": "namHoc", "hoc_ky": "hocKy", "ma_hp": "maHP", "ten_hp": "tenHP",
              "so_tc": "soTC", "diem_10": "diem10", "diem_chu": "diemChu"}

_lock = threading.RLock()


def _dumps(v) -> str | None:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _loads(s):
    return None if s is None else json.loads(s)


def _int_if_whole(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _turso_row_factory(cursor, row):
    del cursor
    return row


class Store:
    def __init__(self, path: str | Path, database_url: str | None = None, auth_token: str | None = None):
        if bool(database_url) != bool(auth_token):
            raise ValueError("TURSO_DATABASE_URL and TURSO_AUTH_TOKEN must both be configured")
        self.path = str(path)
        self.database_url = database_url
        self.auth_token = auth_token
        if not self.database_url:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        c = self.connect()
        try:
            c.executescript(SCHEMA.read_text(encoding="utf-8"))
        finally:
            c.close()

    def connect(self, *, foreign_keys: bool = True):
        if self.database_url:
            import turso_serverless

            c = turso_serverless.connect(self.database_url, auth_token=self.auth_token, isolation_level=None)
            c.row_factory = _turso_row_factory
            if foreign_keys:
                c.execute("PRAGMA foreign_keys = ON")
            return c
        c = sqlite3.connect(self.path, timeout=30, isolation_level=None)  # tự quản lý giao dịch
        c.row_factory = sqlite3.Row
        if foreign_keys:
            c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        return c

    def is_empty(self) -> bool:
        c = self.connect(foreign_keys=False)
        try:
            return c.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0
        finally:
            c.close()

    # ------------------------------------------------------------------ nạp
    def load(self, c: sqlite3.Connection) -> E.Db:
        db = E.Db()
        st = {r["key"]: json.loads(r["value"]) for r in c.execute("SELECT key, value FROM settings")}
        db.config = {**E.DEFAULT_CONFIG, **st.get("config", {})}
        db.seq = {**db.seq, **st.get("seq", {})}
        db.clock_offset = int(st.get("clockOffset", 0))
        db.fault = bool(st.get("fault", False))
        db.students = [{v: r[k] for k, v in STUDENT_COLS.items()} for r in c.execute("SELECT * FROM students ORDER BY rowid")]
        for r in c.execute("SELECT * FROM grades ORDER BY rowid"):
            g = {v: r[k] for k, v in GRADE_COLS.items()}
            g["soTC"] = _int_if_whole(g["soTC"])
            if isinstance(g["diem10"], int):
                g["diem10"] = float(g["diem10"])
            g["diemChu"] = g["diemChu"] or ""
            db.grades.append(g)
        hist: dict[str, list] = {}
        for r in c.execute("SELECT * FROM request_history ORDER BY request_id, seq"):
            hist.setdefault(r["request_id"], []).append(
                {"t": r["t"], "step": r["step"], "actor": r["actor"], "note": r["note"] or "", "kind": r["kind"]})
        for r in c.execute("SELECT * FROM requests ORDER BY created_at, id"):
            req = {"id": r["id"], "status": r["status"], "createdAt": r["created_at"], "updatedAt": r["updated_at"],
                   "attempts": r["attempts"], "transcriptVersions": r["transcript_versions"],
                   "decisionNote": r["decision_note"] or "", "approvedBy": r["approved_by"], "history": hist.get(r["id"], [])}
            for col, key in REQ_JSON.items():
                req[key] = _loads(r[col])
            req["acks"] = req["acks"] or []
            req["feedback"] = req["feedback"] or []
            req["timers"] = req["timers"] or {}
            req["autoChecks"] = req["autoChecks"] or []
            db.requests.append(req)
        db.outbox = [{"id": r["id"], "t": r["t"], "to": r["to_addr"], "toRole": r["to_role"], "subject": r["subject"],
                      "body": r["body"], "reqId": r["request_id"], "step": r["step"], "delivery": r["delivery"]}
                     for r in c.execute("SELECT * FROM emails ORDER BY id")]
        db.logs = [{"id": r["id"], "t": r["t"], "level": r["level"], "msg": r["msg"], "reqId": r["request_id"],
                    "actor": r["actor"]} for r in c.execute("SELECT * FROM audit_logs ORDER BY id")]
        db.archive = [{"code": r["code"], "reqId": r["request_id"], "mssv": r["mssv"], "hash": r["hash"],
                       "signature": r["signature"], "keyId": r["key_id"], "signedAt": r["signed_at"],
                       "transcript": json.loads(r["transcript_json"])}
                      for r in c.execute("SELECT * FROM signed_transcripts ORDER BY signed_at")]
        db.issuance = [{"t": r["t"], "reqId": r["request_id"], "mssv": r["mssv"], "hoTen": r["ho_ten"], "code": r["code"],
                        "dienTu": True, "soBanGiay": r["so_ban_giay"], "mucDich": r["muc_dich"],
                        "approvedBy": r["approved_by"], "leadTimeH": r["lead_time_h"]}
                       for r in c.execute("SELECT * FROM issuance ORDER BY id")]
        return db

    # ------------------------------------------------------------------ ghi
    def _executemany(self, c, sql: str, rows) -> None:
        if not self.database_url:
            c.executemany(sql, rows)
            return
        rows = list(rows)
        if not rows:
            return
        prefix, values = sql.rsplit(" VALUES ", 1)
        parameters_per_row = values.count("?")
        if not parameters_per_row:
            raise ValueError("Bulk insert SQL must contain positional parameters")
        batch_size = max(1, 900 // parameters_per_row)
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            placeholders = ",".join(values for _ in batch)
            parameters = [value for row in batch for value in row]
            c.execute(f"{prefix} VALUES {placeholders}", parameters)

    def save(self, c: sqlite3.Connection, db: E.Db) -> None:
        for t in ("issuance", "signed_transcripts", "request_history", "emails", "audit_logs", "requests", "grades",
                  "students", "settings"):
            c.execute(f"DELETE FROM {t}")
        self._executemany(c, "INSERT INTO settings(key, value) VALUES (?, ?)", [
            ("config", _dumps(db.config)), ("seq", _dumps(db.seq)), ("clockOffset", _dumps(db.clock_offset)),
            ("fault", _dumps(bool(db.fault))),
        ])
        self._executemany(c, f"INSERT INTO students({','.join(STUDENT_COLS)}) VALUES ({','.join('?' * len(STUDENT_COLS))})",
                      [[s.get(v) for v in STUDENT_COLS.values()] for s in db.students])
        self._executemany(c, f"INSERT INTO grades({','.join(GRADE_COLS)}) VALUES ({','.join('?' * len(GRADE_COLS))})",
                      [[g.get(v) for v in GRADE_COLS.values()] for g in db.grades])
        cols = ["id", "mssv", "status", "created_at", "updated_at", "attempts", "transcript_versions", "decision_note",
                "approved_by", *REQ_JSON]
        rows, hist = [], []
        for r in db.requests:
            rows.append([r["id"], r["form"]["mssv"], r["status"], r["createdAt"], r["updatedAt"], r["attempts"],
                         r["transcriptVersions"], r.get("decisionNote"), r.get("approvedBy"),
                         *[_dumps(r.get(k)) for k in REQ_JSON.values()]])
            hist += [(r["id"], i, h["t"], h["step"], h["actor"], h["note"], h["kind"]) for i, h in enumerate(r["history"])]
        self._executemany(c, f"INSERT INTO requests({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", rows)
        self._executemany(c, "INSERT INTO request_history(request_id, seq, t, step, actor, note, kind) VALUES (?,?,?,?,?,?,?)", hist)
        self._executemany(c, "INSERT INTO emails(id, t, to_addr, to_role, subject, body, request_id, step, delivery) VALUES (?,?,?,?,?,?,?,?,?)",
                      [(m["id"], m["t"], m["to"], m["toRole"], m["subject"], m["body"], m["reqId"], m["step"], m.get("delivery"))
                       for m in db.outbox])
        self._executemany(c, "INSERT INTO audit_logs(id, t, level, msg, request_id, actor) VALUES (?,?,?,?,?,?)",
                      [(l["id"], l["t"], l["level"], l["msg"], l["reqId"], l.get("actor")) for l in db.logs])
        self._executemany(c, "INSERT INTO signed_transcripts(code, request_id, mssv, hash, signature, key_id, signed_at, transcript_json) VALUES (?,?,?,?,?,?,?,?)",
                      [(a["code"], a["reqId"], a["mssv"], a["hash"], a["signature"], a.get("keyId"), a["signedAt"],
                        _dumps(a["transcript"])) for a in db.archive])
        self._executemany(c, "INSERT INTO issuance(t, request_id, mssv, ho_ten, code, so_ban_giay, muc_dich, approved_by, lead_time_h) VALUES (?,?,?,?,?,?,?,?,?)",
                      [(x["t"], x["reqId"], x["mssv"], x["hoTen"], x["code"], x["soBanGiay"], x["mucDich"], x["approvedBy"],
                        x["leadTimeH"]) for x in db.issuance])

    @contextmanager
    def session(self, signer=None, on_email=None, write: bool = True):
        """Nạp và xử lý một snapshot; tuần tự hóa writers bằng khóa của cơ sở dữ liệu."""
        with _lock:
            c = self.connect(foreign_keys=write)
            try:
                if write:
                    c.execute("BEGIN IMMEDIATE")
                db = self.load(c)
                db.store_connection = c
                db.signer, db.on_email = signer, on_email
                yield db
                if write:
                    self.save(c, db)
                    c.execute("COMMIT")
            except Exception:
                if c.in_transaction:
                    c.execute("ROLLBACK")
                raise
            finally:
                c.close()


# ----------------------------------------------------------------- tài khoản
def list_users(c: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT id, username, full_name, role, department, mssv, active FROM users ORDER BY role, username")]


def get_user(c: sqlite3.Connection, user_id: int) -> dict | None:
    r = c.execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()
    return dict(r) if r else None


def find_user(c: sqlite3.Connection, username: str) -> dict | None:
    username = username.strip()
    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    normalized_name = normalize(username)
    if not normalized_name:
        return None

    username_key = username.lower()
    exact_matches = c.execute(
        "SELECT * FROM users WHERE active = 1 AND "
        "(username = ? OR (role = 'SV' AND full_name = ?)) "
        "ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END LIMIT 2",
        (username_key, username, username_key),
    ).fetchall()
    username_match = next((row for row in exact_matches if row["username"] == username_key), None)
    if username_match:
        return dict(username_match)
    if len(exact_matches) == 1:
        return dict(exact_matches[0])

    matches = [
        row for row in c.execute("SELECT * FROM users WHERE role = 'SV' AND active = 1")
        if normalize(row["full_name"]) == normalized_name
    ]
    return dict(matches[0]) if len(matches) == 1 else None


def upsert_user(c: sqlite3.Connection, username: str, password_hash: str | None, full_name: str, role: str,
                department: str | None = None, mssv: str | None = None) -> None:
    username = username.strip().lower()
    row = c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        c.execute("UPDATE users SET full_name = ?, role = ?, department = ?, mssv = ?, active = 1 WHERE id = ?",
                  (full_name, role, department, mssv, row["id"]))
        if password_hash:
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, row["id"]))
    else:
        c.execute("INSERT INTO users(username, password_hash, full_name, role, department, mssv, created_at) VALUES (?,?,?,?,?,?,?)",
                  (username, password_hash, full_name, role, department, mssv, int(time.time() * 1000)))
