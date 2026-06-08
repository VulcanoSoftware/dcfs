import pytest

from dcfs.errors.dcfs import LoginFailed


class TestBasicAuth:
    def test_authenticate_no_users_returns_anonymous(self, mocker):
        mock_get_config = mocker.patch("dcfs.auth.basic.get_config")
        from dcfs.auth.basic import authenticate
        from dcfs.auth.user import ReadonlyUser

        mock_config = mocker.Mock()
        mock_config.dcfs.users = None
        mock_get_config.return_value = mock_config

        user = authenticate("any_user", "any_password")

        assert isinstance(user, ReadonlyUser)
        assert user.username == "anonymous"

    def test_authenticate_no_username_raises_error(self, mocker):
        mock_get_config = mocker.patch("dcfs.auth.basic.get_config")
        from dcfs.auth.basic import authenticate

        mock_user_config = mocker.Mock()
        mock_config = mocker.Mock()
        mock_config.dcfs.users = {"test": mock_user_config}
        mock_get_config.return_value = mock_config

        with pytest.raises(LoginFailed, match="Anonymous login is disabled"):
            authenticate("", "password")

    def test_authenticate_valid_admin_user(self, mocker):
        mock_get_config = mocker.patch("dcfs.auth.basic.get_config")
        from dcfs.auth.basic import authenticate
        from dcfs.auth.user import AdminUser

        mock_user_config = mocker.Mock()
        mock_user_config.password = "correct_password"
        mock_user_config.readonly = False
        mock_config = mocker.Mock()
        mock_config.dcfs.users = {"admin": mock_user_config}
        mock_get_config.return_value = mock_config

        user = authenticate("admin", "correct_password")

        assert isinstance(user, AdminUser)
        assert user.username == "admin"
        assert user.readonly is False

    def test_authenticate_valid_readonly_user(self, mocker):
        mock_get_config = mocker.patch("dcfs.auth.basic.get_config")
        from dcfs.auth.basic import authenticate
        from dcfs.auth.user import ReadonlyUser

        mock_user_config = mocker.Mock()
        mock_user_config.password = "correct_password"
        mock_user_config.readonly = True
        mock_config = mocker.Mock()
        mock_config.dcfs.users = {"readonly": mock_user_config}
        mock_get_config.return_value = mock_config

        user = authenticate("readonly", "correct_password")

        assert isinstance(user, ReadonlyUser)
        assert user.username == "readonly"
        assert user.readonly is True

    def test_authenticate_invalid_username(self, mocker):
        mock_get_config = mocker.patch("dcfs.auth.basic.get_config")
        from dcfs.auth.basic import authenticate

        mock_user_config = mocker.Mock()
        mock_user_config.password = "correct_password"
        mock_config = mocker.Mock()
        mock_config.dcfs.users = {"valid_user": mock_user_config}
        mock_get_config.return_value = mock_config

        with pytest.raises(
            LoginFailed,
            match="No such user \\(invalid_user\\) or password is incorrect",
        ):
            authenticate("invalid_user", "any_password")

    def test_authenticate_invalid_password(self, mocker):
        mock_get_config = mocker.patch("dcfs.auth.basic.get_config")
        from dcfs.auth.basic import authenticate

        mock_user_config = mocker.Mock()
        mock_user_config.password = "correct_password"
        mock_config = mocker.Mock()
        mock_config.dcfs.users = {"valid_user": mock_user_config}
        mock_get_config.return_value = mock_config

        with pytest.raises(
            LoginFailed, match="No such user \\(valid_user\\) or password is incorrect"
        ):
            authenticate("valid_user", "wrong_password")
