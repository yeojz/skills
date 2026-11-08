"""Find the command words of a gh call.

Shared by the guards that judge a gh call, so the subcommand is found past
the persistent `-R o/r` option the same way for each of them. The guards
read the flags that matter to them as literal tokens; gh's own option
parser is not emulated.
"""

import os

# The persistent option that takes a value and may come before the
# subcommand, as in `gh -R o/r pr merge 5`.
PERSISTENT_VALUE_OPTIONS = {"-R", "--repo"}
# Commands whose second word is an operand, not a subcommand.
SINGLE_WORD_COMMANDS = {"api"}


def gh_command(argv):
    """(command words, args) of a gh call, or None for another program.

    The command words are `("pr", "merge")` or `("api",)`, found past any
    option before or between them. The args are every other token in order.
    """
    if not argv or os.path.basename(argv[0]) != "gh":
        return None
    words = []
    args = []
    rest = list(argv[1:])
    while rest:
        token = rest.pop(0)
        if token == "--":
            args.append(token)
            break
        if token.startswith("-") and token != "-":
            args.append(token)
            if token in PERSISTENT_VALUE_OPTIONS and rest:
                args.append(rest.pop(0))
            continue
        words.append(token)
        if len(words) == 2 or words[0] in SINGLE_WORD_COMMANDS:
            break
    return tuple(words), args + rest
