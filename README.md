# Share by URL

Publish a local file as an unguessable link, through a webserver you already run.

```console
$ sharebyurl holiday.jpg
https://example.com/s/debkxsyfz2/holiday.jpg
```

`sharebyurl` creates a directory named with a random token under your public web root and symlinks the file into it. Nothing is copied, so sharing a 4 GB video costs nothing but an inode.

## How it works

A share is one directory of symlinks:

```
/var/www/html/s/
└── london21-9me2gkistk/
    ├── beach.jpg -> /home/you/photos/beach.jpg
    └── pier.jpg  -> /home/you/photos/pier.jpg
```

The directory name is the secret. Ten characters of `[a-z0-9]` is about 52 bits, which is ample against guessing — provided the parent directory does not list its contents. See [Webserver configuration](#webserver-configuration); that part is not optional.

## Installation

Requires Python 3.10 or newer, and a Unix-like system (symlinks on Windows need elevated privileges).

```console
$ uv tool install git+https://github.com/watercrossing/sharebyurl.git
```

Or with pipx, if you prefer:

```console
$ pipx install git+https://github.com/watercrossing/sharebyurl.git
```

Then tell it where shares go, and what URL that directory is served at:

```console
$ sharebyurl --default \
    --public_html /var/www/html/s \
    --public_url https://example.com/s
```

Settings live in `~/.config/sharebyurl.ini` (or `$XDG_CONFIG_HOME`, or `$SHAREBYURL_CONFIG`).

## Usage

| Command | What it does |
|---|---|
| `sharebyurl a.jpg b.jpg` | new share containing both files |
| `sharebyurl -s london21 a.jpg` | new share named `london21-<token>` |
| `sharebyurl -s london21-9me2gkistk b.jpg` | add to that existing share |
| `sharebyurl --slugify "My Photo.JPG"` | link it as `my-photo.jpg` instead |
| `sharebyurl -e 7d a.jpg` | expire the share in a week |
| `sharebyurl --list` | every share, with expiry |
| `sharebyurl --remove <share>` | delete a share (the originals are untouched) |
| `sharebyurl --prune` | delete every share whose expiry has passed |
| `sharebyurl --prune --quiet` | the same, but silent unless it deletes something |

Sharing one file prints the URL to that file; sharing several prints the URL to the directory.

Re-sharing a file that is already in a share is a no-op rather than an error. If the name is taken by a *different* file, `sharebyurl` says so and stops — `--force` replaces it.

### Expiry

`-e` / `--expiry` takes a number and a unit: `30m`, `12h`, `7d`, `4w`, `1y`, or `never`. `m` is minutes; months are not supported, because a calendar month is not a fixed length of time.

`--default --expiry 7d` makes that the default for new shares. An existing share keeps the expiry it was given unless you pass `-e` again.

**Nothing expires on its own** — expiry is recorded, and `--prune` acts on it. To make that automatic, add a line to your user crontab with `crontab -e`:

```cron
17 * * * * $HOME/.local/bin/sharebyurl --prune --quiet
```

`--quiet` matters here: without it an hourly job mails you "Nothing to prune." every hour. With it, an idle run is completely silent and you only hear from cron when a share was actually deleted.

Check it first with `sharebyurl --prune --dry-run`, which reports without deleting.

Prune only ever touches shares it has a record of, so a directory you created by hand under `public_html` is safe. Records live in `~/.local/state/sharebyurl/shares.json` (or `$XDG_STATE_HOME`); deleting that file loses expiry tracking but breaks no live URL.

## Webserver configuration

**The parent directory must not be listable.** Without this, one request to `/s/` enumerates every share you have ever made and the tokens stop being secrets. The share directories themselves *should* list, so that a multi-file share has an index.

Apache:

```apache
<Directory "/var/www/html/s/">
    Options -Indexes +FollowSymLinks
</Directory>
<Directory /var/www/html/s/*/>
    Options Indexes FollowSymLinks
</Directory>
```

nginx:

```nginx
location = /s/ { return 403; }
location /s/  { autoindex on; }
```

Verify it before relying on it: `/s/` should give 403, and `/s/<token>/` a listing.

Two things worth knowing:

- Apache's `FollowSymLinks` is what makes any of this work. `SymLinksIfOwnerMatch` will not do, since the target is owned by you and served by `www-data`.
- The webserver user must be able to read both the target file *and* every directory on the path to it. A file mode `600` in `~/Documents` gives a 403, not a download.

## Shell completion

Completion offers existing share names for `-s` and `--remove`, which is what makes reusable shares practical to type.

If argcomplete's global completion is active, **this works with no shell config at all**. Debian and Ubuntu turn it on when you install `python3-argcomplete`; elsewhere it is a one-off:

```console
$ activate-global-python-argcomplete --user
```

Global completion only runs executables marked `PYTHON_ARGCOMPLETE_OK`. A console script generated from a `[project.scripts]` entry point cannot carry that marker itself, so argcomplete resolves the entry point back to the module and looks there — which is why `sharebyurl/main.py` opens with the marker as its first line. Do not remove it; the tests check for it, because losing it breaks completion silently and only for installed copies.

If you would rather not use global completion, register this one command instead:

```bash
eval "$(register-python-argcomplete sharebyurl)"
```

`sharebyurl --completions` prints the equivalent for zsh, fish and tcsh.

## Development

```console
$ uv sync
$ uv run pytest
$ uv run ruff check . && uv run mypy sharebyurl
```

## Upgrading from 0.3

The CLI and the on-disk layout are unchanged, so existing links keep working. On first run, any `[<share>]` sections in the old config file are moved into the state file and stripped from the config — they only ever recorded `expiry = -1`, so they import as "never expires".

Version 0.3 accepted `-e` but silently ignored it; if you relied on that, note that expiry now actually happens once the prune timer is installed.

## License

MIT — see [LICENSE](LICENSE).
