# PYTHON_ARGCOMPLETE_OK
"""Command line entry point.

The marker above must stay in the first 1024 bytes of this file. The console
script generated from the ``[project.scripts]`` entry point cannot carry it,
so argcomplete's global completion resolves the entry point back to this
module and looks for it here instead -- which is what lets tab completion work
without anyone editing their shell config.

The CLI is flag-driven rather than subcommand-driven so that the bare form --
``sharebyurl photo.jpg`` -- stays the shortest thing to type, and so that
argcomplete keeps seeing every option on one parser. Under subparsers,
completing a share name would mean typing ``sharebyurl add -s <TAB>``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import argcomplete

from . import __version__, completions, config, shares
from .duration import DurationError, format_delta, parse_duration
from .shares import ShareError
from .store import ShareStore


def share_completer(prefix: str, parsed_args: Any = None, **kwargs: Any) -> list[str]:
    """Complete share names from whichever public_html is in play.

    Reads the config on demand, so a ``-p`` on the same command line is
    honoured rather than ignored.
    """
    try:
        override = getattr(parsed_args, "public_html", None)
        public_html = override or config.load().public_html
        if not public_html:
            return []
        return sorted(x.name for x in Path(public_html).iterdir() if x.is_dir())
    except OSError:
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sharebyurl",
        description="Publish local files as unguessable links through your webserver.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--list", action="store_true", help="list every share and its expiry")
    actions.add_argument(
        "--remove",
        metavar="SHARE",
        nargs="+",
        help="delete the named shares and the symlinks in them",
    ).completer = share_completer  # type: ignore[attr-defined]
    actions.add_argument(
        "--prune", action="store_true", help="delete every share whose expiry has passed"
    )
    actions.add_argument(
        "--completions", action="store_true", help="print shell completion setup instructions"
    )

    parser.add_argument(
        "-s",
        "--share",
        help="an existing share to add to, or a tag to prefix a new random share name with",
    ).completer = share_completer  # type: ignore[attr-defined]
    parser.add_argument(
        "-e",
        "--expiry",
        help="how long the share should live, e.g. '7d', '12h', '4w', or 'never'",
    )
    parser.add_argument(
        "-p", "--public_html", type=Path, help="the publicly served directory holding shares"
    )
    parser.add_argument("-u", "--public_url", help="the public URL that public_html is served at")
    parser.add_argument(
        "--slugify", action="store_true", help="rename files to url-friendly equivalents"
    )
    parser.add_argument(
        "--force", action="store_true", help="replace a link that already exists in the share"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="with --prune, report without deleting"
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="with --prune, say nothing when there was nothing to do (for cron)",
    )
    parser.add_argument(
        "--default",
        action="store_true",
        help="save --expiry, --public_html and --public_url as the defaults",
    )
    parser.add_argument("paths", metavar="path", type=Path, nargs="*")

    return parser


def cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)

    try:
        return _run(args)
    except ShareError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except DurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    settings = config.load()

    # Saving defaults happens before public_html is required, so that a fresh
    # install can set public_url on its own.
    if args.default:
        _save_defaults(settings, args)
        if not (args.paths or args.list or args.remove or args.prune):
            return 0

    if args.completions:
        return completions.print_instructions()

    public_html = args.public_html or settings.public_html
    if not public_html:
        raise ShareError(
            "Do not know where to put shares. Configure sharebyurl first:\n"
            "  sharebyurl --default --public_html /var/www/html/s --public_url https://example.com/s"
        )
    public_html = public_html.expanduser()
    if not public_html.is_dir():
        raise ShareError(f"public_html does not exist or is not a directory: {public_html}")

    public_url = args.public_url or settings.public_url

    store = ShareStore.load()
    if settings.legacy_shares:
        imported = store.migrate_from_config(settings.legacy_shares)
        store.save()
        settings.legacy_shares = None
        settings.save()
        print(
            f"Migrated {imported} share(s) from the config file into {store.path}.",
            file=sys.stderr,
        )

    now = datetime.now(timezone.utc)

    if args.list:
        return _list(public_html, store, now)
    if args.remove:
        return _remove(public_html, store, args.remove)
    if args.prune:
        return _prune(public_html, store, now, args.dry_run, args.quiet)

    if not args.paths:
        raise ShareError("Need at least one path to share. See --help.")

    return _add(args, settings, public_html, public_url, store, now)


def _save_defaults(settings: config.Config, args: argparse.Namespace) -> None:
    if args.expiry:
        parse_duration(args.expiry)  # validated now so a bad value is never persisted
        settings.default_expiry = args.expiry
    if args.public_html:
        settings.public_html = args.public_html.expanduser()
    if args.public_url:
        settings.public_url = args.public_url
    settings.save()
    print(f"Defaults written to {settings.path}.")


def _add(
    args: argparse.Namespace,
    settings: config.Config,
    public_html: Path,
    public_url: str,
    store: ShareStore,
    now: datetime,
) -> int:
    expiry_text = args.expiry or settings.default_expiry
    delta = parse_duration(expiry_text) if expiry_text else None
    expires = now + delta if delta else None

    # Validate the sources first: creating the share directory before we know
    # the files exist is how a failed run leaves an empty share behind.
    shares.resolve_sources(args.paths)

    name, existed = shares.resolve_share_name(public_html, args.share)
    dest = public_html / name
    created_dir = not dest.exists()
    dest.mkdir(parents=True, exist_ok=True)

    try:
        result = shares.link_paths(dest, args.paths, use_slug=args.slugify, force=args.force)
    except ShareError:
        if created_dir and not any(dest.iterdir()):
            dest.rmdir()
        raise

    # An explicit --expiry always wins; otherwise an existing share keeps the
    # expiry it already had rather than silently getting the default again.
    record = store.get(name)
    if args.expiry or not (existed and record):
        store.record(name, expires, now=now)
    store.save()

    for skipped in result.already_present:
        print(f"Already shared, left alone: {skipped}", file=sys.stderr)

    _print_share_urls(public_url, name, result.created, dest)

    final = store.get(name)
    if final and final.expires:
        print(
            f"Expires {final.expires:%Y-%m-%d %H:%M %Z} "
            f"(in {format_delta(final.expires - now)}) -- run `sharebyurl --prune` to clear it.",
            file=sys.stderr,
        )
    return 0


def _print_share_urls(public_url: str, name: str, created: list[str], dest: Path) -> None:
    if not public_url:
        print(
            "Warning: public_url is not configured, so no URL can be built. "
            "Set it with `sharebyurl --default --public_url ...`.",
            file=sys.stderr,
        )
        print(dest)
        return

    if len(created) == 1:
        print(shares.share_url(public_url, name, created[0]))
    else:
        print(shares.share_url(public_url, name))


def _list(public_html: Path, store: ShareStore, now: datetime) -> int:
    rows = shares.list_shares(public_html, store)
    if not rows:
        print("No shares yet.")
        return 0

    width = max(len(r.name) for r in rows)
    print(f"{'SHARE'.ljust(width)}  FILES  EXPIRES")
    for row in rows:
        if row.expires is None:
            when = "never" if row.tracked else "never (untracked)"
        elif row.expires <= now:
            when = f"expired {format_delta(now - row.expires)} ago"
        else:
            when = f"in {format_delta(row.expires - now)} ({row.expires:%Y-%m-%d %H:%M})"
        print(f"{row.name.ljust(width)}  {row.files:>5}  {when}")

    orphans = shares.find_orphans(public_html, store)
    if orphans:
        names = ", ".join(sorted(o.name for o in orphans))
        print(f"\nTracked but missing from disk: {names}", file=sys.stderr)
    return 0


def _remove(public_html: Path, store: ShareStore, names: list[str]) -> int:
    failures = 0
    for name in names:
        try:
            shares.delete_share(public_html, name)
        except ShareError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            failures += 1
            continue
        store.forget(name)
        print(f"Removed {name}")
    store.save()
    return 1 if failures else 0


def _prune(
    public_html: Path, store: ShareStore, now: datetime, dry_run: bool, quiet: bool = False
) -> int:
    removed, skipped = shares.prune(public_html, store, now, dry_run=dry_run)
    if not dry_run:
        store.save()

    verb = "Would remove" if dry_run else "Removed"
    for name in removed:
        print(f"{verb} {name}")
    for name, reason in skipped:
        print(f"Skipped {name}: {reason}", file=sys.stderr)

    # An hourly cron job that says "Nothing to prune." every hour is an hourly
    # email. Under --quiet an idle run is completely silent, so mail only
    # arrives when something actually happened.
    if not removed and not skipped and not quiet:
        print("Nothing to prune.")
    return 0
