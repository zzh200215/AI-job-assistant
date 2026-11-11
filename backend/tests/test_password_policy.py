"""Password policy validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import PasswordChangeReq, RegisterReq, TokenPasswordResetReq


class TestPasswordPolicy:
    def _register(self, password: str, username: str = "testuser", email: str = "test@example.com"):
        return RegisterReq(username=username, email=email, password=password, role="candidate")

    def test_strong_password_with_special_char_passes(self):
        req = self._register("StrongP@ssw0rd")
        assert req.password == "StrongP@ssw0rd"

    def test_long_password_with_two_categories_passes(self):
        req = self._register("longpassword1234")
        assert req.password == "longpassword1234"

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            self._register("Short1!")

    def test_letters_only_rejected(self):
        with pytest.raises(ValidationError):
            self._register("onlyletters")

    def test_digits_only_rejected(self):
        with pytest.raises(ValidationError):
            self._register("1234567890")

    def test_blacklisted_password_rejected(self):
        # "p@ssw0rd" is in the blacklist and satisfies 3 categories (lower+digit+special)
        with pytest.raises(ValidationError) as exc_info:
            self._register("p@ssw0rd")
        assert "常见" in str(exc_info.value) or "blacklist" in str(exc_info.value).lower()

    def test_password_matching_username_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            self._register("MyUser123!", username="MyUser123!")
        assert "用户名" in str(exc_info.value)

    def test_password_matching_email_local_part_rejected(self):
        # Password equals email local part (case-insensitive) and satisfies complexity
        # Xyz98765 has upper+lower+digit = 3 categories, not in blacklist
        with pytest.raises(ValidationError) as exc_info:
            self._register("Xyz98765", email="Xyz98765@example.com")
        assert "邮箱" in str(exc_info.value)

    def test_leading_or_trailing_space_rejected(self):
        with pytest.raises(ValidationError):
            self._register(" StrongP@ssw0rd ")

    def test_reset_password_validates_complexity(self):
        with pytest.raises(ValidationError):
            TokenPasswordResetReq(
                token="any-token",
                new_password="weakpass",
                confirm_password="weakpass",
            )

    def test_reset_password_mismatch_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            TokenPasswordResetReq(
                token="any-token",
                new_password="StrongP@ssw0rd",
                confirm_password="DifferentP@ssw0rd",
            )
        assert "不一致" in str(exc_info.value)

    def test_change_password_validates_complexity(self):
        """改密与注册共用同一套密码策略。

        原先那条被删掉的「账号 + 邮箱」改密端点比注册松（只判 >=6 位），
        这条腿钉的是"改密不再是绕过策略的后门"。
        """
        with pytest.raises(ValidationError):
            PasswordChangeReq(
                old_password="StrongP@ssw0rd",
                new_password="weakpass",
                confirm_password="weakpass",
            )

    def test_change_password_rejects_reusing_current_one(self):
        with pytest.raises(ValidationError) as exc_info:
            PasswordChangeReq(
                old_password="StrongP@ssw0rd",
                new_password="StrongP@ssw0rd",
                confirm_password="StrongP@ssw0rd",
            )
        assert "当前密码相同" in str(exc_info.value)
