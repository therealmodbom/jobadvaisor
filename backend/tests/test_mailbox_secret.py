import stat

import pytest
from cryptography.fernet import Fernet

from jobadvaisor.mailbox_secret import PasswordUnreadable, forget, key_configured, read, store

KEY = Fernet.generate_key().decode()


def test_password_round_trips(tmp_path):
    path = tmp_path / "mailbox-password"
    store(path, "app-password-1", KEY)
    assert read(path, KEY) == "app-password-1"


def test_file_has_mode_600(tmp_path):
    path = tmp_path / "mailbox-password"
    store(path, "app-password-1", KEY)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_storing_again_replaces_the_password_and_keeps_mode_600(tmp_path):
    path = tmp_path / "mailbox-password"
    store(path, "first", KEY)
    store(path, "second", KEY)
    assert read(path, KEY) == "second"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [entry.name for entry in tmp_path.iterdir()] == ["mailbox-password"]


def test_the_file_never_holds_the_plain_text(tmp_path):
    path = tmp_path / "mailbox-password"
    store(path, "app-password-1", KEY)
    assert b"app-password-1" not in path.read_bytes()


def test_no_file_means_none(tmp_path):
    assert read(tmp_path / "mailbox-password", KEY) is None


def test_wrong_key_raises_password_unreadable(tmp_path):
    path = tmp_path / "mailbox-password"
    store(path, "app-password-1", KEY)
    with pytest.raises(PasswordUnreadable):
        read(path, Fernet.generate_key().decode())


def test_the_error_text_does_not_hold_the_password(tmp_path):
    path = tmp_path / "mailbox-password"
    store(path, "app-password-1", KEY)
    with pytest.raises(PasswordUnreadable) as caught:
        read(path, Fernet.generate_key().decode())
    assert "app-password-1" not in str(caught.value)


def test_forget_removes_the_file_and_tolerates_none(tmp_path):
    path = tmp_path / "mailbox-password"
    store(path, "app-password-1", KEY)
    forget(path)
    assert not path.exists()
    forget(path)


def test_store_creates_the_missing_directory(tmp_path):
    path = tmp_path / "state" / "mailbox-password"
    store(path, "app-password-1", KEY)
    assert read(path, KEY) == "app-password-1"


@pytest.mark.parametrize("key", [None, "", "not a fernet key", "c2hvcnQ="])
def test_a_malformed_or_missing_key_counts_as_no_key(key):
    assert key_configured(key) is False


def test_a_fernet_key_counts_as_a_key():
    assert key_configured(KEY) is True
