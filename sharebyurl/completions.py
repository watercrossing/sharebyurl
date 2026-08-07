"""Shell completion setup text, printed by ``sharebyurl --completions``."""

from textwrap import dedent

INSTRUCTIONS = dedent(
    """\
    Add the appropriate line to your shell's config file so that it runs on
    startup. You will likely have to restart your shell for completion to
    start working.

    bash:
        eval "$(register-python-argcomplete sharebyurl)"

    zsh:
        Completion for zsh needs bashcompinit enabled first:

        autoload -U bashcompinit
        bashcompinit
        eval "$(register-python-argcomplete sharebyurl)"

    tcsh:
        eval `register-python-argcomplete --shell tcsh sharebyurl`

    fish:
        # Not required in the config file, only run once:
        register-python-argcomplete --shell fish sharebyurl \\
            >~/.config/fish/completions/sharebyurl.fish
    """
)


def print_instructions() -> int:
    print(INSTRUCTIONS)
    return 0
