"""The mailbox password at rest: a Fernet token in one file of the state directory, readable
only with the key from `Settings.mailbox_key` (ADR 0016). The data repository never sees it.

The functions take the key as a string and never put the password or the key into an exception
text. Callers check `key_configured` first: `store` and `read` raise `ValueError` for a
malformed key.
"""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class PasswordUnreadable(Exception):
    """The stored password cannot be decrypted with the configured key (changed or lost key,
    damaged file)."""


def key_configured(key: str | None) -> bool:
    """Whether `key` is a usable Fernet key. A missing or malformed key counts as no key."""
    try:
        Fernet(key or "")
    except ValueError:
        return False
    return True


def store(path: Path, password: str, key: str) -> None:
    """Encrypt `password` with `key` and write it to `path` with mode 600, replacing any earlier
    file by rename and creating the directory. Raises `ValueError` for a malformed key."""
    token = Fernet(key).encrypt(password.encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(token)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read(path: Path, key: str) -> str | None:
    """The password stored at `path`, or `None` when there is no file. Raises
    `PasswordUnreadable` when `key` cannot decrypt it and `ValueError` for a malformed key."""
    fernet = Fernet(key)
    try:
        token = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        return fernet.decrypt(token).decode()
    except InvalidToken:
        raise PasswordUnreadable from None


def forget(path: Path) -> None:
    """Remove the stored password at `path`; nothing happens when there is none."""
    path.unlink(missing_ok=True)
