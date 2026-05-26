"""보안 모듈 단위 테스트 — JWT, bcrypt, 서명."""
import pytest
import os


class TestJWT:
    def test_create_and_decode_access_token(self, rsa_keys, monkeypatch):
        priv, pub = rsa_keys
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", priv)
        monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", pub)
        # 키 재생성 강제
        import importlib, app.core.security as sec
        sec._private_key = None
        sec._public_key = None

        token = sec.create_access_token("user-123", "admin")
        payload = sec.decode_token(token)

        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self, rsa_keys, monkeypatch):
        priv, pub = rsa_keys
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", priv)
        monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", pub)
        import app.core.security as sec
        sec._private_key = None
        sec._public_key = None

        token, jti = sec.create_refresh_token("user-456")
        payload = sec.decode_token(token)

        assert payload["sub"] == "user-456"
        assert payload["jti"] == jti
        assert payload["type"] == "refresh"

    def test_decode_invalid_token_returns_none(self, rsa_keys, monkeypatch):
        priv, pub = rsa_keys
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", priv)
        monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", pub)
        import app.core.security as sec
        sec._private_key = None
        sec._public_key = None

        assert sec.decode_token("not.a.valid.token") is None

    def test_password_hash_and_verify(self):
        from app.core.security import hash_password, verify_password

        pw = "my_super_secret_password_123!"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_enrollment_token_format(self):
        from app.core.security import generate_enrollment_token
        token = generate_enrollment_token()
        assert len(token) >= 32
        assert token.isalnum() or "-" in token or "_" in token


class TestFileSigningAndVerify:
    def test_sign_and_verify(self, tmp_path, rsa_keys):
        priv, pub = rsa_keys
        from app.core.signing import sign_file, verify_signature

        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"hello world patch data")

        sig = sign_file(str(test_file), priv)
        assert sig  # non-empty base64

        assert verify_signature(str(test_file), sig, pub) is True

    def test_tampered_file_fails_verify(self, tmp_path, rsa_keys):
        priv, pub = rsa_keys
        from app.core.signing import sign_file, verify_signature

        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"original content")
        sig = sign_file(str(test_file), priv)

        # 파일 변조
        test_file.write_bytes(b"tampered content")
        assert verify_signature(str(test_file), sig, pub) is False

    def test_wrong_signature_fails(self, tmp_path, rsa_keys):
        priv, pub = rsa_keys
        from app.core.signing import verify_signature

        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"some data")
        assert verify_signature(str(test_file), "aW52YWxpZHNpZ25hdHVyZQ==", pub) is False
