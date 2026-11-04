"""Read a gh call the way gh reads it.

Shared by the hooks that judge a gh call, so the subcommand is found past
persistent options such as `-R o/r`, and a bool option's final value is read
the way pflag leaves it, in the same way for each of them.
"""

import os

# strconv.ParseBool, which pflag applies to every bool assignment.
BOOL_SPELLINGS = {
    "1": True, "t": True, "T": True, "TRUE": True, "true": True, "True": True,
    "0": False, "f": False, "F": False, "FALSE": False, "false": False, "False": False,
}
# The persistent option that takes a value and may come before the
# subcommand, as in `gh -R o/r pr merge 5` (cli/cli v2.103.0).
PERSISTENT_VALUE_OPTIONS = {"-R", "--repo"}
# Commands whose second word is an operand, not a subcommand.
SINGLE_WORD_COMMANDS = {"api"}


def gh_command(argv):
    """(command words, args) of a gh call, or None for another program.

    The command words are `("pr", "merge")` or `("api",)`, found past any
    option before or between them. The args are every other token in order,
    options before the subcommand included, so an option parser still sees
    `-R o/r` and its value.
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


def final_bool_option(args, bool_options, value_options, name):
    """The value pflag leaves in the bool option `name` after reading `args` in order.

    `bool_options` and `value_options` map each long name to its one-letter
    shorthand, or None. A bool option takes an attached =value only; every
    other option consumes the rest of its token or the next token. Returns
    None when gh would reject the line or the hook cannot follow it.
    """
    shorts = {}
    for long_name, letter in bool_options.items():
        if letter:
            shorts[letter] = ("bool", long_name)
    for long_name, letter in value_options.items():
        if letter:
            shorts[letter] = ("value", long_name)
    result = False
    rest = list(args)
    while rest:
        token = rest.pop(0)
        if token == "--":
            break
        if not token.startswith("-") or token == "-":
            continue
        if token.startswith("--"):
            long_name, has_value, raw = token[2:].partition("=")
            if long_name in bool_options:
                if has_value:
                    if raw not in BOOL_SPELLINGS:
                        return None
                    value = BOOL_SPELLINGS[raw]
                else:
                    value = True
                if long_name == name:
                    result = value
            elif long_name in value_options:
                if not has_value:
                    if not rest:
                        return None
                    rest.pop(0)
            else:
                return None
            continue
        cluster = token[1:]
        while cluster:
            letter, cluster = cluster[0], cluster[1:]
            if letter not in shorts:
                return None
            kind, long_name = shorts[letter]
            if kind == "bool":
                if cluster.startswith("="):
                    if cluster[1:] not in BOOL_SPELLINGS:
                        return None
                    value = BOOL_SPELLINGS[cluster[1:]]
                    cluster = ""
                else:
                    value = True
                if long_name == name:
                    result = value
            elif cluster:
                cluster = ""
            elif rest:
                rest.pop(0)
            else:
                return None
    return result
