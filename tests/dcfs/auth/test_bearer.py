import time

import jwt
import pytest

from dcfs.auth.bearer import JWTPayload, authenticate, login
from dcfs.auth.user import AdminUser, ReadonlyUser
from dcfs.errors import LoginFailed


class TestBearerAuth:
    def _setup_mock_config(self, mocker, users=None, jwt_secret="test_secret", jwt_algo="HS256", jwt_life=3600):
        """Helper to mock get_config() for bearer tests."""
        mock_get_config = mocker.patch("dcfs.auth.bearer.get_config")
        mock_config = mocker.Mock()
        mock_config.dcfs.users = users or {}
        mock_config.dcfs.jwt.secret = jwt_secret
        mock_config.dcfs.jwt.algorithm = jwt_algo
        mock_config.dcfs.jwt.life = jwt_life
        mock_get_config.return_value = mock_config
        return mock_config

    def _make_token(self, username, secret="test_secret", algo="HS256", readonly=False, expired=False):
        payload = JWTPayload(
            username=username,
            exp=int(time.time()) - 3600 if expired else int(time.time()) + 3600,
            readonly=readonly,
        )
        return jwt.encode(dict(payload), key=secret, algorithm=algo)

    def test_login_anonymous_when_no_users(self, mocker):
        self._setup_mock_config(mocker, users={})

        token = login("testuser", "testpass")

        payload = jwt.decode(token, key="test_secret", algorithms=["HS256"])
        assert payload["username"] == "anonymous"
        assert payload["readonly"] is True
        assert "exp" in payload

    def test_login_anonymous_disabled(self, mocker):
        mock_user = mocker.Mock()
        mock_user.password = "correctpass"
        mock_user.readonly = False
        self._setup_mock_config(mocker, users={"testuser": mock_user})

        with pytest.raises(LoginFailed, match="Anonymous login is disabled"):
            login("", "anypass")

    def test_login_valid_user(self, mocker):
        mock_user = mocker.Mock()
        mock_user.password = "correctpass"
        mock_user.readonly = False
        self._setup_mock_config(mocker, users={"testuser": mock_user})

        token = login("testuser", "correctpass")

        payload = jwt.decode(token, key="test_secret", algorithms=["HS256"])
        assert payload["username"] == "testuser"
        assert payload["readonly"] is False
        assert "exp" in payload

    def test_login_invalid_user(self, mocker):
        mock_user = mocker.Mock()
        mock_user.password = "correctpass"
        mock_user.readonly = False
        self._setup_mock_config(mocker, users={"testuser": mock_user})

        with pytest.raises(
            LoginFailed, match="No such user \\(nonexistent\\) or password incorrect"
        ):
            login("nonexistent", "anypass")

    def test_login_wrong_password(self, mocker):
        mock_user = mocker.Mock()
        mock_user.password = "correctpass"
        mock_user.readonly = False
        self._setup_mock_config(mocker, users={"testuser": mock_user})

        with pytest.raises(
            LoginFailed, match="No such user \\(testuser\\) or password incorrect"
        ):
            login("testuser", "wrongpass")

    def test_login_readonly_user(self, mocker):
        mock_user = mocker.Mock()
        mock_user.password = "correctpass"
        mock_user.readonly = True
        self._setup_mock_config(mocker, users={"readonly_user": mock_user})

        token = login("readonly_user", "correctpass")

        payload = jwt.decode(token, key="test_secret", algorithms=["HS256"])
        assert payload["username"] == "readonly_user"
        assert payload["readonly"] is True

    def test_authenticate_admin_user(self, mocker):
        self._setup_mock_config(mocker)
        token = self._make_token("admin", readonly=False)

        user = authenticate(token)

        assert isinstance(user, AdminUser)
        assert user.username == "admin"

    def test_authenticate_readonly_user(self, mocker):
        self._setup_mock_config(mocker)
        token = self._make_token("readonly", readonly=True)

        user = authenticate(token)

        assert isinstance(user, ReadonlyUser)
        assert user.username == "readonly"

    def test_authenticate_invalid_token(self, mocker):
        self._setup_mock_config(mocker)

        with pytest.raises(jwt.DecodeError):
            authenticate("invalid.token.here")

    def test_authenticate_expired_token(self, mocker):
        self._setup_mock_config(mocker)
        token = self._make_token("admin", expired=True)

        with pytest.raises(jwt.ExpiredSignatureError):
            authenticate(token)
