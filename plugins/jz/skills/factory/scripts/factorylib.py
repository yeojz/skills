"""Shared code for the factory's `gate` and `job` scripts.

Holds what both scripts must agree on: how a spec is parsed, how the config
is layered, how git is called, and the gate itself. The gate lives here so
that `job merge` and `job final` run the same checks as the `gate` command
without spawning it and reading its output back.

Everything a job could change to its own advantage (the spec, the criteria's
commands, `factory.json`) is read from the base ref with `git show`, never
from the job's worktree.
"""

import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
DEFAULT_CONFIG = os.path.join(os.path.dirname(SCRIPT_DIR), "config.json")
REPO_CONFIG = "factory.json"

# A check that never returns would hold a concurrency slot for the rest of
# the run, so every command the gate starts is bounded. A repository raises
# or lowers it with `check_timeout` in factory.json.
CHECK_TIMEOUT_SECONDS = 1800
LOG_TAIL_LINES = 80

LOCK_FILES = [
    ("pnpm-lock.yaml", "pnpm run"),
    ("package-lock.json", "npm run"),
    ("yarn.lock", "yarn run"),
    ("bun.lockb", "bun run"),
    ("bun.lock", "bun run"),
]

# Cheapest first, and the script names the `verify` skill maps to each
# concern, so both flows run the same declared commands.
CONCERNS = [
    ("typecheck", ["typecheck", "type-check", "tsc", "check-types"]),
    ("lint", ["lint", "lint:ci", "biome:check", "eslint"]),
    ("format", ["format:check", "biome:format", "prettier:check", "format"]),
    ("test", ["test", "test:ci", "validate", "check"]),
    ("build", ["build", "build:ci"]),
]

SKIP_MARKERS = [".skip(", ".only(", "xit(", "xdescribe(", "@pytest.mark.skip", "t.Skip("]

TEST_FILE = re.compile(
    r"(^|/)(tests?|__tests__|spec)/"
    r"|(^|/)test[_-][^/]*$"
    r"|[._-](test|spec)\.[^/]+$"
)

CHECK_KINDS = ("test", "command", "drive", "inspection")
RISKS = ("low", "medium", "high")
SURFACES = ("ui", "security")


class FactoryError(Exception):
    """A missing or malformed input: the spec, the config or a git ref."""


# git

def git(cwd, *args, **options):
    """Run git in `cwd` and return its stdout without the trailing newline.

    Raises FactoryError on a non-zero exit unless `check=False`, in which
    case it returns None.
    """
    check = options.get("check", True)
    done = subprocess.run(
        ["git", "-C", cwd] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if done.returncode != 0:
        if not check:
            return None
        message = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise FactoryError("git %s failed: %s" % (args[0], message[-1] if message else "exit %d" % done.returncode))
    return done.stdout.decode("utf-8", "replace").rstrip("\n")


def repo_root(path):
    start = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    root = git(start, "rev-parse", "--show-toplevel", check=False)
    if not root:
        raise FactoryError("%s is not inside a git repository" % path)
    return os.path.realpath(root)


def show(cwd, ref, path):
    """The file's text at `ref`, or None when the ref does not hold it."""
    return git(cwd, "show", "%s:%s" % (ref, path), check=False)


def has_remote(cwd, name="origin"):
    remotes = git(cwd, "remote", check=False) or ""
    return name in remotes.split()


def default_branch(cwd):
    """The branch `refs/remotes/origin/HEAD` names, or None when it is unset."""
    ref = git(cwd, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False)
    if ref and ref.startswith("origin/"):
        return ref[len("origin/"):]
    return None


def sha_matches(claimed, head):
    """True when `claimed` is the head commit, in full or as a prefix of 7 or more."""
    claimed = (claimed or "").strip().lower()
    return len(claimed) >= 7 and re.fullmatch(r"[0-9a-f]+", claimed) is not None and head.startswith(claimed)


# files

def write_atomic(path, text):
    """Replace `path` in one rename, so a reader never sees half a file."""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def read_json(path):
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def write_json(path, value):
    write_atomic(path, json.dumps(value, indent=2) + "\n")


# config

def load_config(cwd, base, defaults_path=None):
    """The defaults file, with each key `factory.json` at `base` sets laid over it."""
    path = defaults_path or DEFAULT_CONFIG
    try:
        config = read_json(path)
    except (OSError, ValueError) as failure:
        raise FactoryError("cannot read config %s: %s" % (path, failure))
    override = show(cwd, base, REPO_CONFIG)
    if override is not None:
        try:
            layered = json.loads(override)
        except ValueError as failure:
            raise FactoryError("%s at %s is not valid JSON: %s" % (REPO_CONFIG, base, failure))
        if not isinstance(layered, dict):
            raise FactoryError("%s at %s is not a JSON object" % (REPO_CONFIG, base))
        # A repository adds to what is protected; it cannot take a default
        # away, since the merge refusal rests on this list.
        for key in ("protected_branches", "protected_paths"):
            if key in layered:
                defaults = list(config.get(key, []))
                layered[key] = defaults + [entry for entry in layered[key] if entry not in defaults]
        config.update(layered)
    protected = list(config.get("protected_branches", []))
    default = default_branch(cwd)
    if default and default not in protected:
        protected.append(default)
    config["protected_branches"] = protected
    return config


def route_reviewers(config, risk, surfaces):
    """Risk reviewers, then each surface's, in config order without repeats."""
    names = list(config.get("reviewers", {}).get(risk, []))
    for surface in surfaces:
        names.extend(config.get("surface_reviewers", {}).get(surface, []))
    ordered = []
    for name in names:
        if name not in ordered:
            ordered.append(name)
    return ordered


def matches_any(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


# spec

def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def spec_slug(spec_path):
    name = os.path.basename(spec_path)
    return name[:-3] if name.endswith(".md") else name


def job_id(step):
    return "%02d-%s" % (step["number"], slugify(step["title"])[:48].strip("-"))


def split_row(line):
    """Split a markdown table row into cells.

    A pipe inside backticks or written as `\\|` belongs to the cell, since a
    criterion's command may pipe. A row with an unpaired backtick falls back
    to splitting on every unescaped pipe.
    """
    def cells(honour_backticks):
        found, current, in_code, index = [], [], False, 0
        while index < len(line):
            char = line[index]
            if char == "\\" and index + 1 < len(line) and line[index + 1] == "|":
                current.append("|")
                index += 2
                continue
            if char == "`" and honour_backticks:
                in_code = not in_code
            if char == "|" and not in_code:
                found.append("".join(current).strip())
                current = []
            else:
                current.append(char)
            index += 1
        found.append("".join(current).strip())
        # The text before the first pipe and after the last is not a cell.
        return found[1:-1], in_code

    result, unpaired = cells(True)
    if unpaired:
        result, _ = cells(False)
    return result


def parse_spec(text):
    """Parse the parts of a spec the factory acts on.

    Returns a dict with `title`, `status`, `requirements` (id to dropped
    flag), `criteria` (rows in table order) and `steps` (in spec order).
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = text.splitlines()
    spec = {"title": "", "status": "", "requirements": {}, "criteria": [], "steps": []}
    section = None
    step = None
    requirement = None
    for line in lines:
        heading = re.match(r"^## +(.*\S)\s*$", line)
        if heading:
            section = heading.group(1).lower()
            step = None
            requirement = None
            continue
        if section is None:
            if not spec["title"] and line.startswith("# "):
                spec["title"] = line[2:].strip()
            found = re.match(r"^Status:\s*(.*\S)\s*$", line)
            if found and not spec["status"]:
                spec["status"] = found.group(1)
            continue
        if section == "requirements":
            found = re.match(r"^- \*\*(R\d+)\b", line)
            if found:
                requirement = found.group(1)
                spec["requirements"][requirement] = False
            if requirement and "(dropped" in line:
                spec["requirements"][requirement] = True
            continue
        if section == "criteria":
            if not line.lstrip().startswith("|"):
                continue
            cells = split_row(line.strip())
            if len(cells) < 5 or not re.fullmatch(r"C\d+\.\d+", cells[0]):
                continue
            check = cells[4]
            kind = re.match(r"^(%s):" % "|".join(CHECK_KINDS), check)
            # Only a test or command check is run; backticks in a drive or
            # inspection cell name a file, not a command.
            runnable = kind is not None and kind.group(1) in ("test", "command")
            command = re.search(r"`([^`]+)`", check) if runnable else None
            spec["criteria"].append({
                "id": cells[0],
                "reqs": re.findall(r"R\d+", cells[1]),
                "kind": kind.group(1) if kind else "unknown",
                "check": check,
                "command": command.group(1).strip() if command else None,
                "dropped": "(dropped" in line,
            })
            continue
        if section == "steps":
            found = re.match(r"^### +Step (\d+): *(.*\S)\s*$", line)
            if found:
                step = {
                    "number": int(found.group(1)), "title": found.group(2), "status": "",
                    "serves": [], "blocked_by": [], "owns": [], "owns_text": None,
                    "review_gate": None, "risk": None, "surfaces": None,
                }
                spec["steps"].append(step)
                continue
            field = re.match(r"^- ([A-Za-z][A-Za-z ]*?):\s*(.*)$", line)
            if step is None or not field:
                continue
            key, value = field.group(1).lower(), field.group(2).strip()
            if key == "status":
                step["status"] = value
            elif key == "serves":
                step["serves"] = re.findall(r"R\d+", value)
            elif key == "blocked by":
                step["blocked_by"] = [int(number) for number in re.findall(r"Step (\d+)", value)]
            elif key == "owns":
                step["owns_text"] = value
                step["owns"] = re.findall(r"`([^`]+)`", value)
            elif key == "review gate":
                step["review_gate"] = value
            elif key == "risk":
                step["risk"] = value.lower()
            elif key == "surfaces":
                step["surfaces"] = [part.strip().lower() for part in value.split(",") if part.strip()]
    return spec


def find_step(spec, number):
    for step in spec["steps"]:
        if step["number"] == number:
            return step
    return None


def criteria_for(spec, reqs=None):
    """The live criteria serving `reqs`, or every live one when `reqs` is None."""
    rows = [row for row in spec["criteria"] if not row["dropped"]]
    if reqs is None:
        return rows
    return [row for row in rows if set(row["reqs"]) & set(reqs)]


def ineligible_reason(spec, step):
    """Why the factory will not run this step, or None when it will."""
    gate = (step["review_gate"] or "").strip().lower()
    if gate != "none":
        return "review gate: %s" % (step["review_gate"] or "no Review gate line")
    if step["risk"] not in RISKS:
        return "no Risk line reading low, medium or high"
    if step["surfaces"] is None:
        return "no Surfaces line"
    unknown = [surface for surface in step["surfaces"] if surface != "none" and surface not in SURFACES]
    if unknown:
        return "unknown surface %s" % ", ".join(unknown)
    if not step["owns"]:
        # Without a path the gate has nothing to hold the job's diff to.
        return "Owns names no path in backticks"
    serves = [req for req in step["serves"] if not spec["requirements"].get(req, False)]
    if not serves:
        return "serves no requirement"
    for req in serves:
        rows = criteria_for(spec, [req])
        if not rows:
            return "requirement %s has no criterion" % req
        for row in rows:
            if row["kind"] == "inspection":
                return "criterion %s of %s is an inspection" % (row["id"], req)
            if row["kind"] == "unknown":
                return "criterion %s of %s has no test, command, drive or inspection check" % (row["id"], req)
    return None


def step_surfaces(step):
    return [surface for surface in (step["surfaces"] or []) if surface != "none"]


# gate

def owned(path, owns):
    for entry in owns:
        if path == entry or path.startswith(entry.rstrip("/") + "/") or fnmatch.fnmatchcase(path, entry):
            return True
    return False


def changed_files(worktree, diff_base):
    """(status, old path, new path) for every file the branch changed.

    The three-dot range compares HEAD with its merge base, so commits that
    reached the base after the branch was cut are not counted as the job's.
    """
    raw = git(worktree, "diff", "--name-status", "-M", "-z", "%s...HEAD" % diff_base)
    parts = raw.split("\0") if raw else []
    changes, index = [], 0
    while index < len(parts) and parts[index]:
        status = parts[index][0]
        if status in ("R", "C"):
            changes.append((status, parts[index + 1], parts[index + 2]))
            index += 3
        else:
            changes.append((status, parts[index + 1], parts[index + 1]))
            index += 2
    return changes


def path_violations(changes, config, owns, owns_text, check_owns):
    reasons, notes = [], []
    protected = config.get("protected_paths", [])
    for status, old, new in changes:
        if status in ("M", "D", "T") and matches_any(old, protected):
            reasons.append("protected path %s: %s" % ("deleted" if status == "D" else "edited", old))
        elif status == "R" and matches_any(old, protected):
            reasons.append("protected path renamed: %s" % old)
        # An added spec could be a second copy of the criteria, so the one
        # directory that holds them takes no new file either.
        if status in ("A", "R", "C") and new.startswith("docs/specs/"):
            reasons.append("file added under docs/specs/: %s" % new)
        elif status in ("A", "R", "C") and matches_any(new, protected):
            reasons.append("protected path added: %s" % new)
    if not check_owns:
        return reasons, notes
    if not owns:
        notes.append("Owns names no path in backticks (%s); the Owns check was skipped" % (owns_text or "no Owns line"))
        return reasons, notes
    for status, old, new in changes:
        touched = [new] if status in ("A", "C") else sorted({old, new})
        for path in touched:
            if not owned(path, owns):
                reasons.append("outside Owns: %s" % path)
    return reasons, notes


def declared_checks(worktree, config):
    """The commands to run as (name, command or None, why not)."""
    explicit = config.get("checks") or []
    if explicit:
        found = []
        for entry in explicit:
            if isinstance(entry, dict):
                found.append((entry.get("name") or entry["command"], entry["command"], ""))
            else:
                found.append((entry, entry, ""))
        return found, []
    manifest = os.path.join(worktree, "package.json")
    if os.path.isfile(manifest):
        try:
            scripts = read_json(manifest).get("scripts") or {}
        except (OSError, ValueError):
            return [], ["package.json is not valid JSON"]
        prefix = None
        for lock, runner in LOCK_FILES:
            if os.path.isfile(os.path.join(worktree, lock)):
                prefix = runner
                break
        found, problems = [], []
        for concern, names in CONCERNS:
            script = next((name for name in names if name in scripts), None)
            if script is None:
                found.append((concern, None, "no script"))
            elif prefix is None:
                # Guessing a package manager would run a command the repo
                # never declared; skipping it would pass a branch unchecked.
                problems.append("package.json declares %s but no lock file names the package manager" % script)
            else:
                found.append((concern, "%s %s" % (prefix, script), ""))
        return found, problems
    targets = set()
    makefile = os.path.join(worktree, "Makefile")
    if os.path.isfile(makefile):
        with open(makefile, encoding="utf-8", errors="replace") as source:
            for line in source:
                target = re.match(r"^([A-Za-z0-9_-]+)\s*:(?!=)", line)
                if target:
                    targets.add(target.group(1))
    found = []
    for concern, names in CONCERNS:
        target = next((name for name in names if name in targets), None)
        if target is None:
            found.append((concern, None, "no script"))
        else:
            found.append((concern, "make %s" % target, ""))
    return found, []


def run_command(command, worktree, timeout, log):
    """Run one shell command in the worktree; returns (exit code, seconds)."""
    log.append("$ %s" % command)
    started = time.time()
    shell = shutil.which("bash") or "/bin/sh"
    try:
        done = subprocess.run(
            [shell, "-c", command], cwd=worktree, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
        code = done.returncode
        output = done.stdout
    except subprocess.TimeoutExpired as expired:
        code = 124
        output = (expired.stdout or b"") + ("\ntimed out after %d seconds\n" % timeout).encode()
    seconds = time.time() - started
    text = output.decode("utf-8", "replace").rstrip("\n")
    if text:
        log.extend(text.split("\n"))
    log.append("exit=%d (%.1fs)" % (code, seconds))
    log.append("")
    return code, seconds


def escalations(worktree, diff_base, changes, config, step):
    """Hard escalation conditions, worded so the same condition reads the same every round.

    `job answer` records the reasons the owner was asked about; an identical
    reason in a later round is then already answered, so no reason carries a
    number that moves between rounds.
    """
    reasons = []
    patterns = config.get("escalate_paths", [])
    for status, old, new in changes:
        for path in sorted({old, new}):
            if matches_any(path, patterns):
                reasons.append("escalate path changed: %s" % path)
        if status == "D" and TEST_FILE.search(old):
            reasons.append("test file deleted: %s" % old)
    current = None
    flagged = []
    # The branch controls .gitattributes and its file names, so the diff is
    # forced to text and unquoted, and the changed lines are counted from
    # the patch: --numstat reports none for a file marked binary.
    diff = git(worktree, "-c", "core.quotePath=false", "diff", "--text", "--no-ext-diff", "--no-textconv",
               "-U0", "--no-color", "%s...HEAD" % diff_base)
    total = 0
    in_hunk = False
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            in_hunk = False
            current = None
        elif line.startswith("@@"):
            in_hunk = True
        elif not in_hunk and line.startswith("+++ "):
            name = line[4:].rstrip("\t")
            if len(name) > 1 and name.startswith('"') and name.endswith('"'):
                name = name[1:-1]
            current = name[2:] if name.startswith("b/") else None
        elif in_hunk and line.startswith(("+", "-")):
            total += 1
            if line.startswith("+") and current and current not in flagged:
                if any(marker in line for marker in SKIP_MARKERS):
                    flagged.append(current)
    for path in flagged:
        reasons.append("skip marker added: %s" % path)
    cap = config.get("diff_line_cap")
    if cap is not None and total > cap:
        reasons.append("diff over the cap of %d changed lines" % cap)
    if step is not None:
        if step["risk"] == "high":
            reasons.append("risk is high")
        if "security" in step_surfaces(step):
            reasons.append("security surface")
    unique = []
    for reason in reasons:
        # The ESCALATE line separates reasons with a semicolon.
        reason = reason.replace(";", ",").replace("\n", " ")
        if reason not in unique:
            unique.append(reason)
    return unique, total


def run_gate(worktree, spec_path, step_number, base, diff_base, defaults_path=None, finished_reqs=None):
    """Gate the worktree's HEAD and return the result as a dict.

    `base` is where the spec and `factory.json` are read from. `diff_base`
    is what the branch's changes are measured against; it differs from
    `base` once other jobs have merged into the integration branch.
    `step_number` None gates a whole spec with no Owns check: it runs the
    criteria of `finished_reqs`, the requirements whose every step is in the
    branch, and lists the rest as not run.

    Raises FactoryError when an input is missing.
    """
    for ref in (base, diff_base):
        if git(worktree, "rev-parse", "--verify", "--quiet", "%s^{commit}" % ref, check=False) is None:
            raise FactoryError("ref %s does not name a commit" % ref)
    text = show(worktree, base, spec_path)
    if text is None:
        raise FactoryError("spec %s is not in %s" % (spec_path, base))
    spec = parse_spec(text)
    step = None
    if step_number is not None:
        step = find_step(spec, step_number)
        if step is None:
            raise FactoryError("spec %s at %s has no Step %d" % (spec_path, base, step_number))
    config = load_config(worktree, base, defaults_path)
    timeout = config.get("check_timeout", CHECK_TIMEOUT_SECONDS)
    head = git(worktree, "rev-parse", "HEAD")
    log = ["gate of %s at %s, spec %s from %s, changes since %s" % (
        "Step %d" % step_number if step else "the whole spec", head, spec_path, base, diff_base), ""]

    changes = changed_files(worktree, diff_base)
    reasons, notes = path_violations(
        changes, config, step["owns"] if step else [], step["owns_text"] if step else None, step is not None)

    checks = []
    found, problems = declared_checks(worktree, config)
    reasons.extend(problems)
    for name, command, why in found:
        if command is None:
            checks.append({"name": name, "command": why, "exit": None, "seconds": None})
            continue
        code, seconds = run_command(command, worktree, timeout, log)
        checks.append({"name": name, "command": command, "exit": code, "seconds": seconds})
        if code != 0:
            reasons.append("check %s failed (exit %d)" % (name, code))

    criteria = []
    for row in criteria_for(spec, step["serves"] if step else None):
        entry = {"id": row["id"], "reqs": row["reqs"], "kind": row["kind"], "command": row["command"],
                 "exit": None, "seconds": None}
        unfinished = step is None and finished_reqs is not None and not set(row["reqs"]) <= set(finished_reqs)
        if row["kind"] in ("test", "command") and not unfinished:
            if not row["command"]:
                reasons.append("criterion %s has no command in backticks" % row["id"])
            else:
                entry["exit"], entry["seconds"] = run_command(row["command"], worktree, timeout, log)
                if entry["exit"] != 0:
                    reasons.append("criterion %s failed (exit %d)" % (row["id"], entry["exit"]))
        criteria.append(entry)

    escalate, changed_lines = escalations(worktree, diff_base, changes, config, step)
    return {
        "verdict": "FAIL" if reasons else "PASS",
        "commit": head,
        "reasons": reasons,
        "escalate": escalate,
        "notes": notes,
        "checks": checks,
        "criteria": criteria,
        "changes": changes,
        "changed_lines": changed_lines,
        "spec": spec_path,
        "step": step_number,
        "base": base,
        "diff_base": diff_base,
        "log": log,
    }


def cell(text):
    return str(text).replace("|", "\\|")


def render_report(result):
    """The text of `checks.md`: three header lines, a summary, then the detail."""
    escalate = "; ".join(result["escalate"]) or "none"
    ran = [check for check in result["checks"] if check["exit"] is not None]
    criteria_run = [row for row in result["criteria"] if row["exit"] is not None]
    target = "Step %d of %s" % (result["step"], result["spec"]) if result["step"] else "Every criterion of %s" % result["spec"]
    path_failures = [reason for reason in result["reasons"]
                     if reason.startswith(("protected path", "file added under", "outside Owns"))]
    lines = [
        "GATE: %s" % result["verdict"],
        "COMMIT: %s" % result["commit"],
        "ESCALATE: %s" % escalate,
        "",
        "## Summary",
        "",
        "- %s, with the spec and config read from `%s` and the changes measured since `%s`." % (
            target, result["base"], result["diff_base"]),
        "- Paths: %d changed files, %d changed lines, %d protected path or Owns failures." % (
            len(result["changes"]), result["changed_lines"], len(path_failures)),
        "- Declared checks: %d run, %d failed, %d with no script." % (
            len(ran), len([check for check in ran if check["exit"] != 0]), len(result["checks"]) - len(ran)),
        "- Criteria: %d run, %d failed, %d not run." % (
            len(criteria_run), len([row for row in criteria_run if row["exit"] != 0]),
            len(result["criteria"]) - len(criteria_run)),
        "- Escalation: %s." % escalate,
        "",
        "## Failures",
        "",
    ]
    lines.extend(["- %s" % reason for reason in result["reasons"]] or ["None."])
    for note in result["notes"]:
        lines.extend(["", "Note: %s." % note])
    lines.extend(["", "## Declared checks", "", "| Check | Command | Exit | Seconds |", "|---|---|---|---|"])
    for check in result["checks"]:
        if check["exit"] is None:
            lines.append("| %s | %s | not run | |" % (cell(check["name"]), cell(check["command"])))
        else:
            lines.append("| %s | `%s` | %d | %.1f |" % (
                cell(check["name"]), cell(check["command"]), check["exit"], check["seconds"]))
    lines.extend(["", "## Criteria", "", "| ID | Req | Check | Command | Exit | Seconds |", "|---|---|---|---|---|---|"])
    for row in result["criteria"]:
        command = "`%s`" % cell(row["command"]) if row["command"] else ""
        if row["exit"] is None:
            lines.append("| %s | %s | %s | %s | not run | |" % (row["id"], ", ".join(row["reqs"]), row["kind"], command))
        else:
            lines.append("| %s | %s | %s | %s | %d | %.1f |" % (
                row["id"], ", ".join(row["reqs"]), row["kind"], command, row["exit"], row["seconds"]))
    lines.extend(["", "## Changed files", ""])
    lines.extend(["- %s `%s`" % (status, new) for status, _, new in result["changes"]] or ["None."])
    tail = result["log"][-LOG_TAIL_LINES:]
    lines.extend(["", "## Log, last %d lines" % LOG_TAIL_LINES, "", "```text"])
    lines.extend(line.replace("```", "'''") for line in tail)
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_report(result, directory, name="checks"):
    """Write `<name>.md` and `<name>.log` into `directory`; returns the report path."""
    os.makedirs(directory, exist_ok=True)
    write_atomic(os.path.join(directory, name + ".log"), "\n".join(result["log"]) + "\n")
    report = os.path.join(directory, name + ".md")
    write_atomic(report, render_report(result))
    return report


def verdict_line(result):
    """The one line a caller reads: the verdict, then the reasons or the commit."""
    if result["verdict"] == "FAIL":
        return "GATE: FAIL %s" % "; ".join(result["reasons"])
    return "GATE: PASS %s escalate: %s" % (result["commit"], "; ".join(result["escalate"]) or "none")
