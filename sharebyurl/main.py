import argparse
import os, sys
from typing import Any, List
import argcomplete
import configparser
import string
import secrets
import re
from textwrap import dedent
from slugify import slugify
from pathlib import Path

SBU_CFG = Path.home() / '.config/sharebyurl.ini'
### need some form of configuration file which stores the webpath (probably default 'public_html/s'?)

config = configparser.ConfigParser()
config.add_section('config')
if SBU_CFG.exists():
    config.read(SBU_CFG)
else:
    SBU_CFG.parent.mkdir(exist_ok=True)

SBU_PUBLIC_HTML = config.get('config', 'public_html', fallback='')
SBU_PUBLIC_HTML = Path(SBU_PUBLIC_HTML) if SBU_PUBLIC_HTML else None
SBU_PUBLIC_URL = config.get('config', 'public_url', fallback='')
SBU_EXPIRY = config.getint('config', 'default_expiry', fallback=-1)

ALLOWED_CHARS_PATTERN = re.compile(r'[^-a-z0-9\.]+')

def generate_token():
    alphabet = string.ascii_lowercase + string.digits
    ## length 10 should be enough to make online attacks infeasable? But really guessing attempts should be throttled, with fail2ban or something.
    return ''.join(secrets.choice(alphabet) for _ in range(10))

class ShareCompleter(object):
    def __init__(self):
        print("Initializing sharecompleter")
        if SBU_PUBLIC_HTML:
            self.choices = [x.name for x in SBU_PUBLIC_HTML.iterdir() if x.is_dir()]
        else:
            self.choices = []
        
    def __call__(self, prefix: str, **kwargs: Any) -> List[str]:
        return self.choices


def get_command_parser() -> argparse.ArgumentParser:

    print("At get_command_parser")
    parser = argparse.ArgumentParser(description='Create symlink to arguments in secret path')
    #TODO: add command that removes expired links, perhaps with a mutually exclusive command group to all of the below
    parser.add_argument('-s', '--share', help='Either specify an existing share or specify a tag to which a random string will be appended').completer = ShareCompleter()
    parser.add_argument('-e', '--expiry', help='Specify how long the link should be alive for, overwriting the default')
    parser.add_argument('-p', '--public_html', type=Path, help='Specify the publicly accessible webshare folder, overwriting the default')
    parser.add_argument('-u', '--public_url', help='Specify the public URL to the public_html folder, overwriting the default')
    parser.add_argument('--slugify', action='store_true', help='slugify all files to make better urls')
    parser.add_argument('--default', action='store_true', help='Store options --expiry and --public_html as defaults')
    parser.add_argument('paths', metavar='path', type=Path, nargs='*')

    #TODO: provide a `completions` command, similar to pipx
    
    return parser

def save_defaults(args):
    if args.expiry:
        config.set('config', 'default_expiry', args.expiry)
    if args.public_html:
        config.set('config', 'public_html', str(args.public_html))
    if args.public_url:
        config.set('config', 'public_url', args.public_url)
    with SBU_CFG.open('w') as f:
        config.write(f)
    print("Default config set.")

def get_expiration_timestamp(expiry : str):
    pass

def cli():
    parser = get_command_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if not SBU_PUBLIC_HTML and not args.public_html:
        # TODO: there must be a more standard way of throwing this error
        print("Do not know where to put the symlink. Please configure sharebyurl first, by running `sharebyurl --default`, specfifying at least --public_html")
        sys.exit(1)
    
    # TODO: need to parse expiry string into an integeger somehow (offer option in h, d, w, y)?
    if args.expiry:
        expiry = -1
    else:
        expiry = SBU_EXPIRY
    
    public_html : Path
    if args.public_html:
        public_html = args.public_html
    else:
        public_html = SBU_PUBLIC_HTML

    if not public_html.exists():
        print("Error: public_html: %s does not exist." %public_html)
        sys.exit(1)
    
    if args.public_url:
        public_url = args.public_url
    else:
        public_url = SBU_PUBLIC_URL

    if args.default:
        save_defaults(args)
        if not args.paths:
            sys.exit(0)
    elif not args.paths:
        # TODO: there must be a more standard way of throwing this error - something like the error if nargs='+' and no argument is given
        print("Need to specify at least path.")
        sys.exit(1)


    if args.share:
        if (public_html / args.share).exists():
            secretShare = args.share
        else:
            secretShare = slugify(args.share) + '-' + generate_token()
    else:
        secretShare = generate_token()
    
    destDir : Path = public_html / secretShare
    if not destDir.exists():
        destDir.mkdir()

    needToSetExpiry = True
    if secretShare not in config.sections:
        config.add_section(secretShare)
    else:
        needToSetExpiry = config.getint(secretShare, 'expiry')
    
    if needToSetExpiry:
        config.set(secretShare, 'expiry', str(expiry))
        with SBU_CFG.open('w') as f:
            config.write(f)
    
    # TODO: Could add option to walk the shared path and create symlink for each file. This would be more Windows friendly.
    for p in args.paths:
        rp : Path = p.resolve()
        if args.slugify:
            (destDir / slugify(rp.name, regex_pattern=ALLOWED_CHARS_PATTERN)).symlink_to(rp)
        (destDir / rp.name).symlink_to(rp)
    
    if len(args.paths) == 1:
        print("%s/%s/%s" %(public_url.rstrip('/'), secretShare, slugify(args.paths[0].name, regex_pattern=ALLOWED_CHARS_PATTERN) if args.slugify else args.paths[0].name))
    else:
        print("%s/%s" %(public_url.rstrip('/'), secretShare))
    sys.exit(0)




completion_instructions = dedent(
    """
Add the appropriate command to your shell's config file
so that it is run on startup. You will likely have to restart
or re-login for the autocompletion to start working.
bash:
    eval "$(register-python-argcomplete sharebyurl)"
zsh:
    To activate completions for zsh you need to have
    bashcompinit enabled in zsh:
    autoload -U bashcompinit
    bashcompinit
    Afterwards you can enable completion for sharebyurl:
    eval "$(register-python-argcomplete sharebyurl)"
tcsh:
    eval `register-python-argcomplete --shell tcsh sharebyurl`
fish:
    # Not required to be in the config file, only run once
    register-python-argcomplete --shell fish sharebyurl >~/.config/fish/completions/sharebyurl.fish
"""
)
