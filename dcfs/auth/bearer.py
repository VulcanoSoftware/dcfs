import time
from typing import TypedDict

import jwt

from dcfs.config import get_config
from dcfs.errors import LoginFailed

from .user import AdminUser, ReadonlyUser, User


class JWTPayload(TypedDict):
    username: str
    exp: int
    readonly: bool


def _jwt_config():
    return get_config().dcfs.jwt


def _dcfs_config():
    return get_config().dcfs


def login(username: str, password: str) -> str:
    jwt_cfg = _jwt_config()
    dcfs_cfg = _dcfs_config()
    if not dcfs_cfg.users:
        return jwt.encode(
            dict(
                JWTPayload(
                    username="anonymous",
                    exp=int(time.time()) + jwt_cfg.life,
                    readonly=True,
                )
            ),
            key=jwt_cfg.secret,
            algorithm=jwt_cfg.algorithm,
        )
    if not username:
        raise LoginFailed("Anonymous login is disabled.")
    if (user := dcfs_cfg.users.get(username)) and user.password == password:
        return jwt.encode(
            dict(
                JWTPayload(
                    username=username,
                    exp=int(time.time()) + jwt_cfg.life,
                    readonly=user.readonly,
                )
            ),
            key=jwt_cfg.secret,
            algorithm=jwt_cfg.algorithm,
        )
    raise LoginFailed(f"No such user ({username}) or password incorrect.")


def authenticate(token: str) -> User:
    jwt_cfg = _jwt_config()
    payload: JWTPayload = jwt.decode(
        token, key=jwt_cfg.secret, algorithms=[jwt_cfg.algorithm]
    )

    username = payload["username"]
    return AdminUser(username) if not payload["readonly"] else ReadonlyUser(username)
