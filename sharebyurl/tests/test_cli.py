"""End-to-end tests driving the real cli() against a sandboxed HOME."""

import contextlib
import json

from sharebyurl.main import cli


class TestHelpAndVersion:
    def test_help_names_the_command_not_the_interpreter(self, capsys):
        # Under `python -m pytest`, argparse 3.14 derives prog from the module
        # unless it is set explicitly.
        with contextlib.suppress(SystemExit):
            cli(["--help"])
        assert "usage: sharebyurl" in capsys.readouterr().out

    def test_completions_prints_setup_text(self, capsys):
        assert cli(["--completions"]) == 0
        assert "register-python-argcomplete sharebyurl" in capsys.readouterr().out


class TestCompletionMarker:
    def test_marker_is_in_the_first_kilobyte_of_the_module(self):
        """Global completion resolves the entry point back to this module.

        Deleting the marker breaks tab completion silently, and only for
        people who installed the package -- never in the working tree.
        """
        import sharebyurl.main

        with open(sharebyurl.main.__file__) as handle:
            assert "PYTHON_ARGCOMPLETE_OK" in handle.read(1024)

    def test_entry_point_still_matches_what_the_checker_expects(self):
        # _check_console_script greps the generated script for these exact
        # strings, so the entry point must stay `sharebyurl.main:cli`.
        from importlib.metadata import entry_points

        scripts = [e for e in entry_points(group="console_scripts") if e.name == "sharebyurl"]
        assert scripts, "sharebyurl console script not installed"
        assert scripts[0].value == "sharebyurl.main:cli"


class TestConfiguration:
    def test_unconfigured_run_explains_itself(self, sandbox, capsys):
        assert cli([str(sandbox.file("a.txt"))]) == 1
        assert "Configure sharebyurl first" in capsys.readouterr().err

    def test_public_url_alone_can_be_saved(self, sandbox, capsys):
        # In 0.3 this exited before saving, so a fresh install could not set
        # public_url without also passing public_html.
        assert cli(["--default", "--public_url", "https://example.com/s"]) == 0
        assert "public_url = https://example.com/s" in sandbox.config_file.read_text()

    def test_bad_default_expiry_is_never_persisted(self, sandbox):
        assert cli(["--default", "--expiry", "next tuesday"]) == 1
        assert not sandbox.config_file.exists()

    def test_missing_public_html_directory_is_reported(self, sandbox, capsys):
        cli(["--default", "--public_html", str(sandbox.root / "nope")])
        assert cli([str(sandbox.file("a.txt"))]) == 1
        assert "does not exist" in capsys.readouterr().err


class TestSharing:
    def test_shares_a_file_and_prints_its_url(self, configured, capsys):
        assert cli([str(configured.file("a.txt"))]) == 0
        out = capsys.readouterr().out.strip()
        share = configured.only_share()
        assert out == f"https://example.com/s/{share.name}/a.txt"
        assert (share / "a.txt").is_symlink()

    def test_multiple_files_print_the_directory_url(self, configured, capsys):
        a, b = configured.file("a.txt"), configured.file("b.txt")
        assert cli([str(a), str(b)]) == 0
        share = configured.only_share()
        assert capsys.readouterr().out.strip() == f"https://example.com/s/{share.name}"

    def test_readme_reuse_workflow(self, configured, capsys):
        """`-s <tag>` then `-s <full-name>` to add more, per the README."""
        assert cli(["-s", "london21", str(configured.file("a.txt"))]) == 0
        name = configured.only_share().name
        assert name.startswith("london21-")

        assert cli(["-s", name, str(configured.file("b.txt"))]) == 0
        assert configured.share_dirs() == [name]
        assert sorted(p.name for p in (configured.www / name).iterdir()) == ["a.txt", "b.txt"]

    def test_adding_the_same_file_twice_does_not_crash(self, configured, capsys):
        source = configured.file("a.txt")
        cli([str(source)])
        name = configured.only_share().name
        capsys.readouterr()

        assert cli(["-s", name, str(source)]) == 0
        assert "Already shared" in capsys.readouterr().err

    def test_slugify_does_not_also_leave_the_ugly_name(self, configured, capsys):
        assert cli(["--slugify", str(configured.file("My Photo 2024.JPG"))]) == 0
        share = configured.only_share()
        assert sorted(p.name for p in share.iterdir()) == ["my-photo-2024.jpg"]

    def test_missing_file_produces_no_share_and_no_url(self, configured, capsys):
        assert cli([str(configured.src / "ghost.png")]) == 1
        assert configured.share_dirs() == []
        assert "https://" not in capsys.readouterr().out

    def test_share_name_cannot_escape_public_html(self, configured, capsys):
        assert cli(["-s", "../src", str(configured.file("a.txt"))]) == 1
        assert "path separator" in capsys.readouterr().err
        assert not (configured.src / "a.txt").is_symlink()


class TestCopying:
    def test_copy_is_recorded_and_removable(self, configured, capsys):
        source = configured.file("talk.pdf")
        assert cli(["--copy", str(source)]) == 0
        assert "Copied talk.pdf as asked" in capsys.readouterr().err

        share = configured.only_share()
        state = json.loads(configured.state_file.read_text())
        assert state["shares"][share.name]["copies"] == ["talk.pdf"]

        assert cli(["--remove", share.name]) == 0
        assert not share.exists()
        assert source.exists()

    def test_relinking_a_copy_drops_it_from_the_record(self, configured, capsys):
        source = configured.file("talk.pdf")
        cli(["--copy", str(source)])
        share = configured.only_share()
        cli(["-s", share.name, "--force", str(configured.file("talk.pdf", "v2"))])

        state = json.loads(configured.state_file.read_text())
        assert "copies" not in state["shares"][share.name]
        assert (share / "talk.pdf").is_symlink()


class TestExpiry:
    def test_expiry_is_recorded(self, configured, capsys):
        assert cli(["-e", "7d", str(configured.file("a.txt"))]) == 0
        name = configured.only_share().name
        state = json.loads(configured.state_file.read_text())
        assert state["shares"][name]["expires"] is not None
        assert "Expires" in capsys.readouterr().err

    def test_bad_expiry_is_rejected_before_anything_is_written(self, configured, capsys):
        assert cli(["-e", "7 fortnights", str(configured.file("a.txt"))]) == 1
        assert configured.share_dirs() == []

    def test_default_expiry_applies_to_new_shares(self, configured):
        cli(["--default", "--expiry", "7d"])
        cli([str(configured.file("a.txt"))])
        name = configured.only_share().name
        state = json.loads(configured.state_file.read_text())
        assert state["shares"][name]["expires"] is not None

    def test_never_means_never(self, configured):
        assert cli(["-e", "never", str(configured.file("a.txt"))]) == 0
        name = configured.only_share().name
        state = json.loads(configured.state_file.read_text())
        assert state["shares"][name]["expires"] is None

    def test_prune_removes_expired_shares(self, configured, capsys):
        cli(["-e", "1m", str(configured.file("a.txt"))])
        name = configured.only_share().name

        # Rewrite the record into the past rather than sleeping.
        state = json.loads(configured.state_file.read_text())
        state["shares"][name]["expires"] = "2020-01-01T00:00:00+00:00"
        configured.state_file.write_text(json.dumps(state))

        capsys.readouterr()
        assert cli(["--prune"]) == 0
        assert f"Removed {name}" in capsys.readouterr().out
        assert configured.share_dirs() == []

    def test_prune_leaves_unexpired_shares(self, configured, capsys):
        cli(["-e", "7d", str(configured.file("a.txt"))])
        assert cli(["--prune"]) == 0
        assert len(configured.share_dirs()) == 1

    def test_quiet_prune_says_nothing_when_idle(self, configured, capsys):
        # An hourly cron job must not mail "Nothing to prune." every hour.
        cli(["-e", "7d", str(configured.file("a.txt"))])
        capsys.readouterr()
        assert cli(["--prune", "--quiet"]) == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_quiet_prune_still_reports_removals(self, configured, capsys):
        cli(["-e", "1m", str(configured.file("a.txt"))])
        name = configured.only_share().name
        state = json.loads(configured.state_file.read_text())
        state["shares"][name]["expires"] = "2020-01-01T00:00:00+00:00"
        configured.state_file.write_text(json.dumps(state))

        capsys.readouterr()
        assert cli(["--prune", "--quiet"]) == 0
        assert f"Removed {name}" in capsys.readouterr().out


class TestListAndRemove:
    def test_list_shows_shares_and_expiry(self, configured, capsys):
        cli(["-e", "7d", str(configured.file("a.txt"))])
        name = configured.only_share().name
        capsys.readouterr()

        assert cli(["--list"]) == 0
        out = capsys.readouterr().out
        assert name in out
        assert "in 6 days" in out or "in 7 days" in out

    def test_list_marks_untracked_directories(self, configured, capsys):
        (configured.www / "legacy").mkdir()
        assert cli(["--list"]) == 0
        assert "untracked" in capsys.readouterr().out

    def test_remove_deletes_the_share_and_its_record(self, configured, capsys):
        source = configured.file("a.txt")
        cli([str(source)])
        name = configured.only_share().name

        assert cli(["--remove", name]) == 0
        assert configured.share_dirs() == []
        assert json.loads(configured.state_file.read_text())["shares"] == {}
        assert source.exists()

    def test_remove_of_unknown_share_fails_cleanly(self, configured, capsys):
        assert cli(["--remove", "nosuchshare"]) == 1
        assert "No such share" in capsys.readouterr().err


class TestMigration:
    def test_legacy_share_sections_move_into_the_store(self, sandbox, capsys):
        sandbox.config_file.write_text(
            "[config]\n"
            f"public_html = {sandbox.www}\n"
            "public_url = https://example.com/s/\n"
            "\n[oldshare1]\nexpiry = -1\n"
            "\n[oldshare2]\nexpiry = -1\n"
        )
        assert cli(["--list"]) == 0

        state = json.loads(sandbox.state_file.read_text())
        assert set(state["shares"]) == {"oldshare1", "oldshare2"}
        assert state["shares"]["oldshare1"]["expires"] is None

        rewritten = sandbox.config_file.read_text()
        assert "[oldshare1]" not in rewritten
        assert "public_url = https://example.com/s/" in rewritten
