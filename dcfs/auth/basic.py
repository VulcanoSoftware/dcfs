from dcfs.config import get_config
from dcfs.errors.dcfs import LoginFailed

from .user import AdminUser, ReadonlyUser, User


def authenticate(username: str, password: str) -> User:
    config = get_config()
    if not config.dcfs.users:
        return ReadonlyUser("anonymous")
    if not username:
        raise LoginFailed("Anonymous login is disabled.")
    if (user := config.dcfs.users.get(username)) and user.password == password:
        return AdminUser(username) if not user.readonly else ReadonlyUser(username)
    raise LoginFailed(f"No such user ({username}) or password is incorrect.")
