"""Máy chủ web Flask: REST API + phục vụ giao diện tĩnh.

Chạy:  python app.py        → http://127.0.0.1:5000

Kiến trúc:
    Trình duyệt (static/)  ──fetch JSON──►  app.py (Flask, xác thực + phân quyền theo làn BPMN)
                                              │
                                              ├─ bangdiem/engine.py   bộ máy quy trình (luật, cổng XOR, timer)
                                              ├─ bangdiem/store.py    SQLite (data/bangdiem.db)
                                              ├─ bangdiem/signing.py  ký số RSA-PSS (keys/)
                                              └─ bangdiem/mailer.py   email: hộp thư + SMTP (tùy chọn)
"""
from __future__ import annotations

import os
import re
import secrets
import sys
import time
import unittest
from functools import wraps
from pathlib import Path

from flask import Flask, Response, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from bangdiem import bpmn
from bangdiem import engine as E
from bangdiem import seed as S
from bangdiem import store as ST
from bangdiem.csvio import parse_any, to_csv
from bangdiem.mailer import Mailer
from bangdiem.signing import Signer

ROOT = Path(__file__).resolve().parent
ROLES = ("SV", "KHOA", "PDT", "PP")
ROLE_LABEL = {"SV": "Sinh viên", "KHOA": "Khoa", "PDT": "Phòng Đào tạo", "PP": "Phó phòng"}
STAFF = [  # tài khoản cán bộ mặc định (mật khẩu demo đặt bằng biến DEMO_PASSWORD)
    ("pdt.hong", "CV. Nguyễn Thị Hồng (PĐT)", "PDT", None),
    ("pp.lethi", "ThS. Lê Thị Phó Phòng", "PP", None),
]


def _load_env_file() -> None:
    """Đọc tệp .env đơn giản (KEY=VALUE) nếu có, không cần thư viện ngoài."""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def khoa_username(dept: str) -> str:
    slug = re.sub(r"[^a-z]+", "", E.strip_diacritics(re.sub(r"^Khoa\s+", "", dept or "", flags=re.I)).lower())
    return f"khoa.{slug or 'chung'}"


def create_app(test_config: dict | None = None) -> Flask:
    _load_env_file()
    app = Flask(__name__, static_folder=None)
    on_vercel = os.environ.get("VERCEL") == "1"
    if on_vercel:
        required = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "FLASK_SECRET_KEY",
                    "SIGN_KEY_PASSPHRASE", "SIGNING_PRIVATE_KEY_B64")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"Vercel environment is missing required settings: {', '.join(missing)}")
    cfg = {
        "DATA_DIR": os.environ.get("DATA_DIR", "/tmp/bangdiem-data" if on_vercel else str(ROOT / "data")),
        "KEY_DIR": os.environ.get("KEY_DIR", "/tmp/bangdiem-keys" if on_vercel else str(ROOT / "keys")),
        "DEMO_MODE": os.environ.get("DEMO_MODE", "1") != "0",
        "DEMO_PASSWORD": os.environ.get("DEMO_PASSWORD", "123456"),
        "SEED_SAMPLE": True,
    }
    cfg.update(test_config or {})
    if cfg["DEMO_MODE"]:
        cfg["DEMO_PASSWORD"] = "123456"
    app.config.update(cfg)
    Path(cfg["DATA_DIR"]).mkdir(parents=True, exist_ok=True)

    # Khóa bí mật cho cookie phiên: lấy từ môi trường, nếu không có thì sinh một lần và cất trong keys/
    secret = os.environ.get("FLASK_SECRET_KEY")
    if not secret:
        sk = Path(cfg["KEY_DIR"]) / "flask_secret.txt"
        sk.parent.mkdir(parents=True, exist_ok=True)
        if not sk.exists():
            sk.write_text(secrets.token_hex(32))
        secret = sk.read_text().strip()
    app.config.update(SECRET_KEY=secret, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1", JSON_SORT_KEYS=False)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    store = ST.Store(
        os.environ.get("DB_PATH", str(Path(cfg["DATA_DIR"]) / "bangdiem.db"))
        if not test_config or "DB_PATH" not in test_config else test_config["DB_PATH"],
        database_url=os.environ.get("TURSO_DATABASE_URL"),
        auth_token=os.environ.get("TURSO_AUTH_TOKEN"),
    )
    signer = Signer(cfg["KEY_DIR"])
    mailer = Mailer()
    flows = bpmn.parse_flows(ROOT / "bpmn" / "BPMN_TO_BE_NHOM5_da_sua.bpmn")
    login_fail: dict[str, list[float]] = {}

    # ------------------------------------------------------------ tài khoản
    def sync_accounts(db: E.Db, c=None) -> None:
        """Đồng bộ tài khoản demo; sinh viên đăng nhập bằng họ tên và MSSV."""
        own = c is None
        c = c or store.connect()
        try:
            pw = generate_password_hash(cfg["DEMO_PASSWORD"])
            existing = {u["username"] for u in ST.list_users(c)}
            sync_demo_credentials = cfg["DEMO_MODE"] and not c.execute(
                "SELECT 1 FROM app_meta WHERE key = ?", ("demo_credentials_v2",)
            ).fetchone()
            demo_credential_hashes = {}
            for username, name, role, dept in STAFF:
                ST.upsert_user(c, username, pw if username not in existing else None, name, role, dept)
                if sync_demo_credentials and username in existing:
                    demo_credential_hashes[username] = pw
            for dept in sorted({s["khoa"] for s in db.students if s["khoa"]}):
                u = khoa_username(dept)
                ST.upsert_user(c, u, pw if u not in existing else None, f"Văn phòng {dept}", "KHOA", dept)
                if sync_demo_credentials and u in existing:
                    demo_credential_hashes[u] = pw
            for s in db.students:
                username = s["mssv"]
                student_pw = None
                if username not in existing:
                    student_pw = generate_password_hash(username) if cfg["DEMO_MODE"] else pw
                elif sync_demo_credentials:
                    demo_credential_hashes[username] = generate_password_hash(username)
                ST.upsert_user(c, username, student_pw, s["hoTen"], "SV", None, username)
            if sync_demo_credentials:
                entries = list(demo_credential_hashes.items())
                if entries:
                    for start in range(0, len(entries), 250):
                        batch = entries[start:start + 250]
                        cases = " ".join("WHEN ? THEN ?" for _ in batch)
                        names = ",".join("?" for _ in batch)
                        params = [value for entry in batch for value in entry]
                        params.extend(username for username, _ in batch)
                        c.execute(
                            f"UPDATE users SET password_hash = CASE username {cases} "
                            f"ELSE password_hash END WHERE username IN ({names})",
                            params,
                        )
                c.execute("INSERT INTO app_meta(key, value) VALUES (?, ?)", ("demo_credentials_v2", "1"))
        finally:
            if own:
                c.close()

    def reset_data(mode: str) -> None:
        with store.session(signer, None) as db:
            fresh = E.Db()
            fresh.signer = signer
            if mode == "sample":
                S.populate_sample(fresh)
            for k in ("config", "students", "grades", "requests", "outbox", "logs", "issuance", "archive", "seq"):
                setattr(db, k, getattr(fresh, k))
            db.clock_offset, db.fault = 0, False
        c = store.connect()
        try:
            c.execute("DELETE FROM users WHERE role = 'SV'")
            with store.session(None, None, write=False) as db:
                sync_accounts(db, c)
        finally:
            c.close()

    if store.is_empty() and cfg["SEED_SAMPLE"]:
        reset_data("sample")
    else:
        with store.session(None, None, write=False) as db:
            sync_accounts(db)

    # ------------------------------------------------------------ tiện ích
    def current_user() -> dict | None:
        uid = session.get("uid")
        if not uid:
            return None
        c = store.connect()
        try:
            return ST.get_user(c, uid)
        finally:
            c.close()

    def api_error(msg: str, status: int):
        return jsonify({"error": msg}), status

    def auth(*roles: str, csrf: bool = True):
        """Bắt buộc đăng nhập + đúng vai trò (làn BPMN). Thao tác ghi phải kèm mã CSRF."""
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                u = current_user()
                if not u:
                    return api_error("Bạn cần đăng nhập", 401)
                if roles and u["role"] not in roles:
                    return api_error(f"Vai trò {ROLE_LABEL[u['role']]} không được thực hiện thao tác này", 403)
                if csrf and request.method != "GET" and request.headers.get("X-CSRF-Token") != session.get("csrf"):
                    return api_error("Phiên làm việc không hợp lệ, hãy tải lại trang", 403)
                g.user = u
                return fn(*a, **kw)
            return wrapper
        return deco

    def body() -> dict:
        return request.get_json(silent=True) or {}

    def dept_of(db: E.Db, req: dict) -> str:
        st = E.find_student(db, req["form"]["mssv"])
        return st["khoa"] if st else ""

    def can_see(u: dict, db: E.Db, req: dict) -> bool:
        if u["role"] == "SV":
            return req["form"]["mssv"] == u["mssv"]
        if u["role"] == "KHOA":
            return dept_of(db, req) == u["department"]
        return True

    def decorate(db: E.Db, req: dict) -> dict:
        out = dict(req)
        out["dept"] = dept_of(db, req)
        out["deadline"] = E.deadline_of(req)
        return out

    def run(fn, write: bool = True):
        """Mở phiên CSDL, quét timer, chạy thao tác; lỗi nghiệp vụ trả về JSON có mã HTTP phù hợp."""
        try:
            with store.session(signer, mailer, write=write) as db:
                fired = E.tick(db)
                if fired and not write:
                    raise _Retry()
                res = fn(db)
                if isinstance(res, tuple):
                    return res
                if isinstance(res, Response):
                    return res
                return jsonify({"fired": fired, **(res or {})})
        except _Retry:
            return run(fn, write=True)
        except E.ProcessError as exc:
            return api_error(str(exc), exc.status)

    def visible_req(db: E.Db, rid: str) -> dict:
        req = E.get_req(db, rid)
        if not can_see(g.user, db, req):
            raise E.ProcessError("Bạn không có quyền với yêu cầu này", 403)
        return req

    # ------------------------------------------------------------ trang tĩnh
    static_dir = ROOT / "static"

    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.get("/<path:p>")
    def static_files(p: str):
        if p.startswith("api/"):
            return api_error("Không tìm thấy", 404)
        return send_from_directory(static_dir, p)

    @app.after_request
    def security_headers(resp: Response):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'")
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ------------------------------------------------------------ xác thực
    @app.post("/api/login")
    def login():
        d = body()
        username = str(d.get("username", "")).strip()
        login_key = username.casefold()
        now_s = time.time()
        fails = [t for t in login_fail.get(login_key, []) if now_s - t < 300]
        if len(fails) >= 5:
            return api_error("Sai mật khẩu quá 5 lần, hãy thử lại sau 5 phút", 429)
        c = store.connect()
        try:
            u = ST.find_user(c, username)
        finally:
            c.close()
        if not u or not check_password_hash(u["password_hash"], str(d.get("password", ""))):
            login_fail[login_key] = fails + [now_s]
            return api_error("Sai tên đăng nhập hoặc mật khẩu", 401)
        login_fail.pop(login_key, None)
        session.clear()
        session["uid"] = u["id"]
        session["csrf"] = secrets.token_urlsafe(24)
        return me()

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/me")
    def me():
        u = current_user()
        if not u:
            demo = None
            if cfg["DEMO_MODE"]:
                c = store.connect()
                try:
                    demo = {"password": cfg["DEMO_PASSWORD"], "accounts": [
                        {
                            "username": x["full_name"] if x["role"] == "SV" else x["username"],
                            "name": x["full_name"], "mssv": x["mssv"],
                            "role": x["role"], "department": x["department"],
                        }
                        for x in ST.list_users(c)]}
                finally:
                    c.close()
            return jsonify({"user": None, "demo": demo})
        return jsonify({"user": {k: u[k] for k in ("id", "username", "full_name", "role", "department", "mssv")},
                        "csrf": session.get("csrf"), "demoMode": cfg["DEMO_MODE"]})

    # ------------------------------------------------------------ danh mục BPMN, tra cứu công khai
    @app.get("/api/bpmn")
    def bpmn_catalog():
        return jsonify({**bpmn.catalog(), "flows": flows})

    @app.get("/api/public-key")
    def public_key():
        return Response(signer.public_pem(), mimetype="application/x-pem-file",
                        headers={"Content-Disposition": "inline; filename=khoa-cong-khai-pdt.pem"})

    @app.get("/api/verify/<code>")
    def verify(code: str):
        def f(db):
            v = E.verify(db, code)
            if not v["found"]:
                return {"found": False}
            e = v["entry"]
            return {"found": True, "valid": v["valid"], "hashOk": v["hashOk"], "signatureOk": v["signatureOk"],
                    "entry": {k: e[k] for k in ("code", "reqId", "signedAt", "hash", "keyId", "transcript")},
                    "algorithm": signer.algorithm}
        return run(f, write=False)

    # ------------------------------------------------------------ trạng thái theo vai trò
    @app.get("/api/state")
    @auth()
    def state():
        u = g.user

        def f(db: E.Db):
            reqs = [decorate(db, r) for r in db.requests if can_see(u, db, r)]
            ids = {r["id"] for r in reqs}
            if u["role"] == "SV":
                st = E.find_student(db, u["mssv"])
                mails = [m for m in db.outbox if m["toRole"] == "SV" and (m["reqId"] in ids or (st and m["to"] == st["email"]))]
                students = [st] if st else []
            elif u["role"] == "KHOA":
                box = E.dept_mailbox(db, u["department"])
                mails = [m for m in db.outbox if m["to"] == box or (m["reqId"] in ids and m["toRole"] == "KHOA")]
                students = [s for s in db.students if s["khoa"] == u["department"]]
            else:
                mails = db.outbox if u["role"] == "PDT" else [m for m in db.outbox if m["toRole"] in ("PP",) or m["step"] in ("t_guidt",)]
                students = db.students
            staff = u["role"] in ("PDT", "PP")
            return {
                "now": E.now(db), "clockOffset": db.clock_offset, "fault": db.fault, "demoMode": cfg["DEMO_MODE"],
                "config": db.config, "stats": E.stats(db) if staff else None,
                "requests": reqs, "outbox": mails, "students": students,
                "issuance": db.issuance if staff else [],
                "recentCodes": [a["code"] for a in db.archive[-4:]][::-1] if staff else [],
                "logs": db.logs[-400:] if u["role"] == "PDT" else [],
                "gradeCounts": {s["mssv"]: len(E.grades_of(db, s["mssv"])) for s in students} if u["role"] == "PDT" else {},
                "signer": {"keyId": signer.key_id, "algorithm": signer.algorithm, "devPassphrase": signer.using_dev_passphrase},
                "smtp": mailer.enabled,
            }
        return run(f, write=False)

    @app.get("/api/requests/<rid>")
    @auth()
    def request_detail(rid: str):
        def f(db):
            req = visible_req(db, rid)
            out = {"request": decorate(db, req)}
            if g.user["role"] != "SV":
                rows = E.grades_of(db, req["form"]["mssv"])
                out["grades"] = rows
                out["liveCheck"] = E.check_grades(db, req["form"]["mssv"], req["acks"])
                out["terms"] = list(dict.fromkeys(f"{r['hocKy']} {r['namHoc']}" for r in
                                                  sorted(rows, key=lambda r: (E.term_order(r), r["maHP"]))))
            return out
        return run(f, write=False)

    @app.get("/api/requests/<rid>/signed.json")
    @auth()
    def signed_package(rid: str):
        def f(db):
            req = visible_req(db, rid)
            if not req.get("signature"):
                raise E.ProcessError("Bảng điểm chưa được ký số", 409)
            resp = jsonify({"transcript": req["transcript"], "signature": req["signature"], "publicKey": signer.public_pem(),
                            "huongDanKiemChung": "Băm SHA-256 chuỗi JSON chuẩn hóa (sort_keys, separators=(',',':'), "
                                                 "ensure_ascii=False) của transcript, rồi kiểm chữ ký RSA-PSS-SHA256 trên "
                                                 "chuỗi hex của giá trị băm bằng publicKey."})
            resp.headers["Content-Disposition"] = f"attachment; filename=bang-diem-{rid}.json"
            return resp
        return run(f, write=False)

    # ------------------------------------------------------------ Sinh viên
    @app.post("/api/requests")
    @auth("SV")
    def create_request():
        d = body()

        def f(db):
            st = E.find_student(db, g.user["mssv"])
            if not st:
                raise E.ProcessError("Tài khoản chưa gắn với hồ sơ sinh viên", 400)
            form = {k: d.get(k) for k in ("hoTen", "ngaySinh", "email", "sdt", "mucDich", "ngonNgu", "banGiay", "soBan", "ghiChu")}
            form["mssv"] = st["mssv"]  # MSSV lấy từ phiên SSO, không tin dữ liệu gửi lên
            req = E.submit_request(db, form, g.user["full_name"])
            return {"request": decorate(db, req)}
        return run(f)

    @app.post("/api/requests/<rid>/supplement")
    @auth("SV")
    def supplement(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.supplement(db, visible_req(db, rid)["id"], d, g.user["full_name"]))})

    @app.post("/api/requests/<rid>/cancel")
    @auth("SV")
    def cancel(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.student_cancel(db, visible_req(db, rid)["id"], d.get("reason", ""), g.user["full_name"]))})

    # ------------------------------------------------------------ Khoa
    @app.post("/api/requests/<rid>/grades/<gid>")
    @auth("KHOA")
    def khoa_grade(rid: str, gid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.khoa_edit_grade(db, visible_req(db, rid)["id"], gid, d, g.user["full_name"]))})

    @app.post("/api/requests/<rid>/acknowledge")
    @auth("KHOA")
    def khoa_ack(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.khoa_acknowledge(db, visible_req(db, rid)["id"], str(d.get("key", "")), g.user["full_name"]))})

    @app.post("/api/requests/<rid>/khoa-decision")
    @auth("KHOA")
    def khoa_decision(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.khoa_decide(db, visible_req(db, rid)["id"], bool(d.get("canFix")), str(d.get("note", "")), g.user["full_name"]))})

    # ------------------------------------------------------------ Phòng Đào tạo
    @app.post("/api/requests/<rid>/qc")
    @auth("PDT")
    def qc(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.qc_decide(db, rid, bool(d.get("ok")), str(d.get("feedback", "")), g.user["full_name"]))})

    @app.post("/api/requests/<rid>/edit")
    @auth("PDT")
    def edit(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.edit_transcript(db, rid, d, g.user["full_name"]))})

    @app.post("/api/requests/<rid>/print")
    @auth("PDT")
    def print_paper(rid: str):
        return run(lambda db: {"request": decorate(db, E.print_paper(db, rid, g.user["full_name"]))})

    @app.post("/api/requests/<rid>/deliver")
    @auth("PDT")
    def deliver(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.confirm_paper(db, rid, str(d.get("receiver", "")), g.user["full_name"]))})

    # ------------------------------------------------------------ Phó phòng
    @app.post("/api/requests/<rid>/pp-decision")
    @auth("PP")
    def pp_decision(rid: str):
        d = body()
        return run(lambda db: {"request": decorate(db, E.pp_decide(db, rid, str(d.get("decision", "")), str(d.get("note", "")), g.user["full_name"]))})

    @app.post("/api/requests/<rid>/stamp")
    @auth("PP")
    def stamp(rid: str):
        return run(lambda db: {"request": decorate(db, E.stamp_paper(db, rid, g.user["full_name"]))})

    # ------------------------------------------------------------ Quản trị (Phòng Đào tạo)
    @app.post("/api/admin/clock")
    @auth(*ROLES)
    def clock():
        d = body()
        if not cfg["DEMO_MODE"] and g.user["role"] != "PDT":
            return api_error("Chỉ Phòng Đào tạo được chỉnh đồng hồ", 403)

        fired_before: list = []

        def f(db):
            if d.get("reset"):
                db.clock_offset = 0
                return {"fired": []}
            return {"fired": fired_before + E.advance_clock(db, int(d.get("ms", 0)))}
        return run(f)

    @app.post("/api/admin/fault")
    @auth("PDT")
    def fault():
        on = bool(body().get("on"))

        def f(db):
            db.fault = on
            E.sys_log(db, "warn" if on else "info", ("Bật" if on else "Tắt") + " giả lập sự cố CSDL điểm", None, g.user["full_name"])
            return {"fault": on}
        return run(f)

    @app.post("/api/admin/config")
    @auth("PDT")
    def update_config():
        d = body()

        def f(db):
            c = db.config
            for k in ("nameSimilarityThreshold", "confidenceThreshold", "warningPenalty", "outlierGap", "supplementDays",
                      "khoaRemindDays", "ppRemindDays", "maxCopies"):
                v = E.to_num(d.get(k))
                if v is not None and v >= 0:
                    c[k] = v
            for k in ("signerName", "emailDomain"):
                if E.norm_space(d.get(k)):
                    c[k] = E.norm_space(d.get(k))
            E.sys_log(db, "audit", "Cập nhật cấu hình ngưỡng", None, g.user["full_name"])
            return {"config": c}
        return run(f)

    @app.post("/api/admin/import/<kind>")
    @auth("PDT")
    def import_data(kind: str):
        d = body()
        if kind not in ("students", "grades"):
            return api_error("Loại dữ liệu không hợp lệ", 400)

        def f(db):
            rows = parse_any(str(d.get("text", "")), kind)
            mode = "replace" if d.get("mode") == "replace" else "merge"
            res = E.import_students(db, rows, mode) if kind == "students" else E.import_grades(db, rows, mode)
            if kind == "students":
                sync_accounts(db, db.store_connection)
            return {"result": res}
        return run(f)

    @app.post("/api/admin/bulk")
    @auth("PDT")
    def bulk():
        d = body()

        def f(db):
            rows = parse_any(str(d.get("text", "")), "requests")
            out = []
            for row in rows:
                def gv(*keys):
                    for k in keys:
                        v = row.get(k)
                        if v is not None and str(v).strip() != "":
                            return v
                    return None
                mssv = str(gv("mssv") or "").strip()
                st = E.find_student(db, mssv) or {}
                ban_giay = re.fullmatch(r"(1|x|co|có|true|yes|y)", str(gv("ban_giay", "banGiay") or ""), re.I) is not None
                r = E.submit_request(db, {
                    "mssv": mssv, "hoTen": gv("ho_ten", "hoTen") or st.get("hoTen", ""),
                    "ngaySinh": gv("ngay_sinh", "ngaySinh") or st.get("ngaySinh", ""),
                    "email": gv("email") or st.get("email", ""), "sdt": gv("sdt") or ("09" + ("00000000" + mssv)[-8:]),
                    "mucDich": gv("muc_dich", "mucDich") or "Theo dữ liệu kiểm thử",
                    "ngonNgu": "en" if re.search(r"en|anh", str(gv("ngon_ngu", "ngonNgu") or ""), re.I) else "vi",
                    "banGiay": ban_giay, "soBan": (gv("so_ban", "soBan") or 1) if ban_giay else 0,
                }, "Nhập hàng loạt")
                failed = [i["msg"] for i in r["validation"]["items"] if not i["ok"]]
                note = "; ".join(failed) if failed else (
                    f"Đối chiếu: {len(r['check']['errors'])} lỗi, {len(r['check']['warnings'])} bất thường" if r["check"] else "")
                out.append({"mssv": mssv, "id": r["id"], "status": r["status"], "note": note})
            return {"results": out}
        return run(f)

    @app.get("/api/admin/grades")
    @auth("PDT")
    def admin_grades():
        mssv = request.args.get("mssv", "")
        return run(lambda db: {"grades": [x for x in db.grades if not mssv or x["mssv"] == mssv][:600], "total": len(db.grades)},
                   write=False)

    @app.get("/api/admin/export/<kind>.csv")
    @auth("PDT")
    def export_csv(kind: str):
        def f(db):
            if kind == "students":
                text = to_csv([{"mssv": s["mssv"], "ho_ten": s["hoTen"], "ngay_sinh": s["ngaySinh"], "gioi_tinh": s["gioiTinh"],
                                "lop": s["lop"], "khoa": s["khoa"], "nganh": s["nganh"], "khoa_hoc": s["khoaHoc"],
                                "email": s["email"], "trang_thai": s["trangThai"]} for s in db.students],
                              ["mssv", "ho_ten", "ngay_sinh", "gioi_tinh", "lop", "khoa", "nganh", "khoa_hoc", "email", "trang_thai"])
            elif kind == "grades":
                text = to_csv([{"mssv": x["mssv"], "nam_hoc": x["namHoc"], "hoc_ky": x["hocKy"], "ma_hp": x["maHP"], "ten_hp": x["tenHP"],
                                "so_tc": x["soTC"], "diem_10": x["diem10"], "diem_chu": x["diemChu"]} for x in db.grades],
                              ["mssv", "nam_hoc", "hoc_ky", "ma_hp", "ten_hp", "so_tc", "diem_10", "diem_chu"])
            elif kind == "issuance":
                text = to_csv(db.issuance, ["t", "reqId", "mssv", "hoTen", "code", "soBanGiay", "mucDich", "approvedBy", "leadTimeH"])
            else:
                raise E.ProcessError("Không có loại dữ liệu này", 404)
            return Response(text, mimetype="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f"attachment; filename={kind}.csv"})
        return run(f, write=False)

    @app.post("/api/admin/reset")
    @auth("PDT")
    def reset():
        mode = "sample" if body().get("mode") == "sample" else "empty"
        reset_data(mode)
        return jsonify({"ok": True, "mode": mode})

    @app.post("/api/admin/run-tests")
    @auth("PDT")
    def run_tests():
        """Chạy bộ kiểm thử tự động ngay trên máy chủ (dùng CSDL tạm, không ảnh hưởng dữ liệu thật)."""
        sys.path.insert(0, str(ROOT))
        suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_quy_trinh")
        results = []

        class Collector(unittest.TestResult):
            def addSuccess(self, test):
                results.append((test, True, ""))

            def addFailure(self, test, err):
                results.append((test, False, str(err[1])))

            def addError(self, test, err):
                results.append((test, False, f"{err[0].__name__}: {err[1]}"))

        suite.run(Collector())
        out = []
        for t, ok, msg in results:
            doc = (t.shortDescription() or t.id()).strip()
            code, _, name = doc.partition(" ")
            out.append({"id": code, "name": name, "test": t.id().split(".")[-1], "pass": ok, "detail": msg})
        out.sort(key=lambda x: x["id"])
        return jsonify({"results": out})

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return api_error("Không tìm thấy", 404)
        return send_from_directory(static_dir, "index.html")

    return app


class _Retry(Exception):
    """Timer vừa kích hoạt trong lời gọi chỉ đọc → chạy lại ở chế độ ghi để lưu kết quả."""


if __name__ == "__main__":
    try:  # tránh lỗi in tiếng Việt trên cửa sổ dòng lệnh Windows cũ
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    application = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"Hệ thống cấp phát bảng điểm: http://{host}:{port}")
    application.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
