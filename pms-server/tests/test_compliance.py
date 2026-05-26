"""컴플라이언스 엔진 단위 테스트 — DB 없이 순수 로직만 검증."""
import pytest
from app.services.compliance import compare_versions


class TestCompareVersions:
    def test_missing_when_installed_is_none(self):
        assert compare_versions(None, "1.0.0") == -1

    def test_missing_when_installed_is_empty(self):
        assert compare_versions("", "1.0.0") == -1

    def test_compliant_same_version(self):
        assert compare_versions("1.0.0", "1.0.0") == 0

    def test_newer_installed(self):
        assert compare_versions("2.0.0", "1.0.0") == 1

    def test_older_installed_is_missing(self):
        assert compare_versions("0.9.0", "1.0.0") == -1

    def test_semver_minor(self):
        assert compare_versions("1.1.0", "1.0.0") == 1
        assert compare_versions("1.0.0", "1.1.0") == -1

    def test_semver_patch(self):
        assert compare_versions("1.0.1", "1.0.0") == 1
        assert compare_versions("1.0.0", "1.0.1") == -1

    def test_multi_digit(self):
        assert compare_versions("10.0.0", "9.9.9") == 1

    def test_non_semver_string_fallback(self):
        # 문자열 비교 폴백 — 같으면 compliant
        assert compare_versions("build-20240101", "build-20240101") == 0

    def test_none_required_is_compliant(self):
        # required 버전이 없으면 항상 compliant
        assert compare_versions("1.0.0", None) == 0

    def test_windows_style_version(self):
        # Windows 버전 형식: 4자리
        assert compare_versions("10.0.19041.1", "10.0.19041.0") == 1
        assert compare_versions("10.0.19041.0", "10.0.19041.1") == -1
