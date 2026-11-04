import base64
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import create_app
from bangdiem.signing import Signer
from bangdiem.store import Store
from turso_serverless.dbapi import Row


class TursoStoreTest(unittest.TestCase):
    def test_requires_url_and_token_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "must both be configured"):
                Store(Path(tmp) / "db.sqlite", database_url="https://db.turso.io")

    def test_remote_connection_uses_turso_driver_without_local_sqlite_settings(self):
        connection = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / "remote" / "db.sqlite"
            with patch("turso_serverless.connect", return_value=connection) as connect:
                Store(local_path, "https://db.turso.io", "test-token")
            self.assertFalse(local_path.parent.exists())

        connect.assert_called_once_with(
            "https://db.turso.io", auth_token="test-token", isolation_level=None
        )
        class Cursor:
            description = (("username", None, None, None, None, None, None),)

        row = Row(Cursor(), ("demo",))
        converted = connection.row_factory(Cursor(), row)
        self.assertEqual(converted["username"], "demo")
        self.assertEqual(dict(converted), {"username": "demo"})
        store = Store.__new__(Store)
        store.database_url = "https://db.turso.io"
        store._executemany(connection, "INSERT INTO users(username, role) VALUES (?, ?)", [
            ("one", "SV"), ("two", "KHOA")
        ])
        self.assertEqual(
            connection.execute.call_args.args,
            ("INSERT INTO users(username, role) VALUES (?, ?),(?, ?)", ["one", "SV", "two", "KHOA"]),
        )
        connection.executemany.assert_not_called()
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertIn("PRAGMA foreign_keys = ON", statements)
        self.assertFalse(any("journal_mode" in statement for statement in statements))
        connection.executescript.assert_called_once()
        connection.close.assert_called_once()

    def test_vercel_requires_durable_storage_and_stable_secrets(self):
        with patch("app._load_env_file"), patch.dict(os.environ, {"VERCEL": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TURSO_DATABASE_URL"):
                create_app()

    def test_vercel_entrypoint_exports_created_flask_app(self):
        entrypoint = Path(__file__).resolve().parents[1] / "api" / "index.py"
        spec = importlib.util.spec_from_file_location("vercel_entrypoint", entrypoint)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        application = object()

        with patch("app.create_app", return_value=application) as create:
            spec.loader.exec_module(module)

        create.assert_called_once_with()
        self.assertIs(module.app, application)

    def test_signing_key_can_be_loaded_from_stable_environment_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Signer(Path(tmp) / "local", passphrase="test-passphrase")
            key_b64 = base64.b64encode(local.key_path.read_bytes()).decode("ascii")
            key_dir = Path(tmp) / "remote"
            with patch.dict(os.environ, {"SIGNING_PRIVATE_KEY_B64": key_b64}):
                remote = Signer(key_dir, passphrase="test-passphrase")

            self.assertEqual(remote.key_id, local.key_id)
            self.assertFalse(key_dir.exists())
            self.assertTrue(remote.verify("test-hash", local.sign("test-hash")))

    def test_signing_key_rejects_invalid_environment_value(self):
        with patch.dict(os.environ, {"SIGNING_PRIVATE_KEY_B64": "not-base64"}):
            with self.assertRaisesRegex(ValueError, "SIGNING_PRIVATE_KEY_B64 is invalid"):
                Signer("unused-key-dir", passphrase="test-passphrase")


if __name__ == "__main__":
    unittest.main()
