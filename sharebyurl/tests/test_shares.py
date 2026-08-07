from datetime import datetime, timedelta, timezone

import pytest

from sharebyurl import shares
from sharebyurl.shares import ShareError
from sharebyurl.store import ShareStore

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)


def store_at(sandbox) -> ShareStore:
    return ShareStore(sandbox.state_file)


class TestShareNames:
    @pytest.mark.parametrize("name", ["../escape", "/tmp", "a/b", "..", "."])
    def test_traversal_is_rejected(self, sandbox, name):
        with pytest.raises(ShareError):
            shares.resolve_share_name(sandbox.www, name)

    def test_absolute_path_cannot_replace_public_html(self, sandbox):
        # pathlib's / operator discards the left side for an absolute right
        # side, which in 0.3 let `-s /tmp` write outside the web root.
        with pytest.raises(ShareError):
            shares.resolve_share_name(sandbox.www, "/tmp")

    def test_new_name_gets_a_slug_and_token(self, sandbox):
        name, existed = shares.resolve_share_name(sandbox.www, "London 21")
        assert not existed
        assert name.startswith("london-21-")
        assert len(name) == len("london-21-") + shares.TOKEN_LENGTH

    def test_existing_share_is_reused_verbatim(self, sandbox):
        (sandbox.www / "london21-abcdefghij").mkdir()
        name, existed = shares.resolve_share_name(sandbox.www, "london21-abcdefghij")
        assert existed
        assert name == "london21-abcdefghij"

    def test_bare_share_is_just_a_token(self, sandbox):
        name, existed = shares.resolve_share_name(sandbox.www, None)
        assert not existed
        assert len(name) == shares.TOKEN_LENGTH


class TestLinking:
    def test_missing_source_shares_nothing(self, sandbox):
        dest = sandbox.www / "share"
        dest.mkdir()
        with pytest.raises(ShareError, match="do not exist"):
            shares.link_paths(dest, [sandbox.src / "nope.png"])
        assert list(dest.iterdir()) == []

    def test_one_bad_path_leaves_no_partial_share(self, sandbox):
        good = sandbox.file("a.txt")
        dest = sandbox.www / "share"
        dest.mkdir()
        with pytest.raises(ShareError):
            shares.link_paths(dest, [good, sandbox.src / "nope.png"])
        assert list(dest.iterdir()) == []

    def test_relinking_the_same_file_is_idempotent(self, sandbox):
        source = sandbox.file("a.txt")
        dest = sandbox.www / "share"
        dest.mkdir()
        shares.link_paths(dest, [source])
        result = shares.link_paths(dest, [source])
        assert result.created == []
        assert result.already_present == ["a.txt"]

    def test_conflicting_name_errors_instead_of_crashing(self, sandbox):
        dest = sandbox.www / "share"
        dest.mkdir()
        first = sandbox.file("a.txt")
        shares.link_paths(dest, [first])

        other_dir = sandbox.root / "other"
        other_dir.mkdir()
        clash = other_dir / "a.txt"
        clash.write_text("different")

        with pytest.raises(ShareError, match="--force"):
            shares.link_paths(dest, [clash])

    def test_force_replaces_the_link(self, sandbox):
        dest = sandbox.www / "share"
        dest.mkdir()
        shares.link_paths(dest, [sandbox.file("a.txt")])

        other_dir = sandbox.root / "other"
        other_dir.mkdir()
        clash = other_dir / "a.txt"
        clash.write_text("different")

        shares.link_paths(dest, [clash], force=True)
        assert (dest / "a.txt").read_text() == "different"

    def test_slugify_creates_only_the_slug(self, sandbox):
        source = sandbox.file("My Photo 2024.JPG")
        dest = sandbox.www / "share"
        dest.mkdir()
        shares.link_paths(dest, [source], use_slug=True)
        assert sorted(p.name for p in dest.iterdir()) == ["my-photo-2024.jpg"]

    def test_two_files_slugifying_to_one_name_is_an_error(self, sandbox):
        a = sandbox.file("My Photo.jpg")
        nested = sandbox.root / "nested"
        nested.mkdir()
        b = nested / "my photo.jpg"
        b.write_text("other")
        dest = sandbox.www / "share"
        dest.mkdir()
        with pytest.raises(ShareError, match="Two different files"):
            shares.link_paths(dest, [a, b], use_slug=True)


class TestDeletion:
    def test_deletes_symlinks_not_targets(self, sandbox):
        source = sandbox.file("a.txt")
        dest = sandbox.www / "share"
        dest.mkdir()
        shares.link_paths(dest, [source])

        shares.delete_share(sandbox.www, "share")
        assert not dest.exists()
        assert source.exists(), "the real file must survive"

    def test_refuses_a_directory_with_real_files(self, sandbox):
        dest = sandbox.www / "share"
        dest.mkdir()
        (dest / "real.txt").write_text("not a symlink")
        with pytest.raises(ShareError, match="real files"):
            shares.delete_share(sandbox.www, "share")
        assert dest.exists()

    def test_refuses_traversal(self, sandbox):
        with pytest.raises(ShareError):
            shares.delete_share(sandbox.www, "../src")
        assert sandbox.src.exists()


class TestPrune:
    def _share_with_expiry(self, sandbox, store, name, expires):
        dest = sandbox.www / name
        dest.mkdir()
        shares.link_paths(dest, [sandbox.file(f"{name}.txt")])
        store.record(name, expires, now=NOW)
        return dest

    def test_removes_only_expired(self, sandbox):
        store = store_at(sandbox)
        live = self._share_with_expiry(sandbox, store, "live", NOW + timedelta(days=1))
        dead = self._share_with_expiry(sandbox, store, "dead", NOW - timedelta(days=1))

        removed, skipped = shares.prune(sandbox.www, store, NOW)

        assert removed == ["dead"]
        assert skipped == []
        assert live.exists() and not dead.exists()

    def test_never_touches_untracked_directories(self, sandbox):
        store = store_at(sandbox)
        stranger = sandbox.www / "not-ours"
        stranger.mkdir()
        self._share_with_expiry(sandbox, store, "dead", NOW - timedelta(days=1))

        shares.prune(sandbox.www, store, NOW)
        assert stranger.exists()

    def test_shares_without_expiry_are_kept(self, sandbox):
        store = store_at(sandbox)
        forever = self._share_with_expiry(sandbox, store, "forever", None)
        removed, _ = shares.prune(sandbox.www, store, NOW)
        assert removed == []
        assert forever.exists()

    def test_dry_run_deletes_nothing(self, sandbox):
        store = store_at(sandbox)
        dead = self._share_with_expiry(sandbox, store, "dead", NOW - timedelta(days=1))
        removed, _ = shares.prune(sandbox.www, store, NOW, dry_run=True)
        assert removed == ["dead"]
        assert dead.exists()
        assert store.get("dead") is not None

    def test_stale_record_for_a_hand_deleted_share_is_dropped(self, sandbox):
        store = store_at(sandbox)
        store.record("gone", NOW - timedelta(days=1), now=NOW)
        removed, skipped = shares.prune(sandbox.www, store, NOW)
        assert removed == []
        assert skipped == [("gone", "already gone, record dropped")]
        assert store.get("gone") is None
