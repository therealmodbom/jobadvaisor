import pytest
from fake_imap import FakeFolder, FakeImap

from jobadvaisor.data.models import Folders
from jobadvaisor.intake.mailbox import Folder, MailboxError, list_folders, searched_folders


def account(**flags) -> FakeImap:
    """Folders by name, each given its flags as a tuple of bytes."""
    return FakeImap({name: FakeFolder(flags=flag) for name, flag in flags.items()})


def test_folders_of_an_account_mark_only_the_trash_folder_as_system():
    imap = account(Posteingang=(), Jobs=(b"\\HasNoChildren",), Papierkorb=(b"\\Trash",))
    assert list_folders(imap) == [Folder("Posteingang", False), Folder("Jobs", False),
                                  Folder("Papierkorb", True)]


def test_a_folder_name_outside_ascii_is_listed_readable():
    assert list_folders(account(Entwürfe=(b"\\Drafts",))) == [Folder("Entwürfe", True)]


def test_a_folder_the_server_marks_not_selectable_is_left_out():
    imap = account(Konten=(b"\\Noselect", b"\\HasChildren"), Gone=(b"\\NonExistent",),
                   Posteingang=())
    assert list_folders(imap) == [Folder("Posteingang", False)]


@pytest.mark.parametrize("flag", [b"\\Trash", b"\\Junk", b"\\Sent", b"\\Drafts", b"\\All",
                                  b"\\Flagged", b"\\Important"])
def test_special_use_flags_mark_a_system_folder(flag):
    assert list_folders(account(Special=(flag,))) == [Folder("Special", True)]


def test_flags_compare_without_case():
    assert list_folders(account(Alle=(b"\\ALL",), Leer=(b"\\NOSELECT",))) == [Folder("Alle", True)]


def test_other_flags_do_not_mark_a_system_folder():
    imap = account(Archiv=(b"\\Archive", b"\\HasNoChildren", b"\\Marked"))
    assert list_folders(imap) == [Folder("Archiv", False)]


def test_listing_failure_is_a_mailbox_error():
    imap = FakeImap({}, errors={"list_folders": OSError("connection lost")})
    with pytest.raises(MailboxError) as caught:
        list_folders(imap)
    assert caught.value.reason == "protocol"


LISTED = [Folder("Posteingang", False), Folder("Jobs", False), Folder("Papierkorb", True),
          Folder("Alle Nachrichten", True)]


def test_all_folders_searches_every_listed_folder_except_the_system_folders():
    assert searched_folders(LISTED, Folders(all=True)) == (["Posteingang", "Jobs"], [])


def test_a_folder_created_later_is_searched_when_all_folders_is_chosen():
    later = [*LISTED, Folder("Jobs 2027", False)]
    assert searched_folders(later, Folders(all=True)) == (["Posteingang", "Jobs", "Jobs 2027"], [])


def test_a_server_without_flags_has_every_folder_searched():
    listed = list_folders(account(Posteingang=(), Jobs=(), Papierkorb=()))
    assert searched_folders(listed, Folders(all=True)) == (["Posteingang", "Jobs", "Papierkorb"],
                                                           [])


def test_chosen_names_are_searched_exactly_system_folder_included():
    chosen = Folders(names=["Alle Nachrichten", "Jobs"])
    assert searched_folders(LISTED, chosen) == (["Alle Nachrichten", "Jobs"], [])


def test_a_chosen_folder_deleted_on_the_server_is_named_and_the_others_searched():
    chosen = Folders(names=["Jobs", "Alt", "Posteingang"])
    assert searched_folders(LISTED, chosen) == (["Jobs", "Posteingang"], ["Alt"])


def test_a_chosen_folder_the_server_now_marks_not_selectable_counts_as_missing():
    listed = list_folders(account(Konten=(b"\\Noselect",), Jobs=()))
    assert searched_folders(listed, Folders(names=["Konten", "Jobs"])) == (["Jobs"], ["Konten"])
