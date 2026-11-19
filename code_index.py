#!/usr/bin/env python3
"""The code index kept healthy, kept current and asked first — by the harness and the runner, not by a brief.

A `/cruise` iteration met all four ways an adopted index fails to be used, with nobody making a mistake. The
database was corrupt when the iteration started, and CodeGraph's own commands did not say so: on a malformed
`codegraph.db`, `codegraph status` reports the index up to date and `codegraph sync` exits 0, and only a query
fails. The watcher that keeps it current was off, which CodeGraph decides for itself in a sandbox. Delegates
reached the index as a deferred tool they had to load by name first, and grepped instead. And nothing counted
which delegate asked it. Each of those is a place a sentence in a brief was the only control.

So this script holds the index at the points the harness and the runner already own:

    python3 scripts/extensions/codegraph/code_index.py health   # open it, integrity-check it, rebuild a corrupt one, sync a stale one
    python3 scripts/extensions/codegraph/code_index.py session  # `health`, said only when it acted
    python3 scripts/extensions/codegraph/code_index.py sync     # a delegate came back; sync
    python3 scripts/extensions/codegraph/code_index.py guard    # a symbol search before the index: refuse it

**Which of those something runs.** `sync` is what the extension's `after-stage` hook does (`hooks/sync.py`,
inside that point's budget), and `health` is what `make check-extensions` runs on a corrupt database before it judges
one and what a person runs to repair an index by hand. `guard` is the extension's `before-search` guard
(`guards/ask_the_index.py`, declared in `extension.json`), which the keel runs before a search in a harness that
can hold one, once a person has agreed to it. `session` was a row the keel's version 1 wrote into Claude Code's
settings and nothing calls it now; it prints only what it did or could not do. The database is ignored by Git and
derived from the source, so a corrupt one loses nothing by being moved aside (to `.codegraph/corrupt/`, the latest
only) and rebuilt. `sync` keeps the index current while an iteration is still editing: after each rung rather than
on CodeGraph's watcher, because the watcher is what was off.

`guard` refuses a search of the source for a symbol — the Grep tool, or `grep`, `rg`, `ag`, `ack` or `git grep`
through the shell — from a session or a delegate that has not asked the index yet, and names the route that
answers instead. A symbol is a name the index holds a definition for, or a name shaped like one (camelCase,
PascalCase with a second hump, snake_case). Words and phrases are prose, and a search confined to documents is text
search, which is right for them: `spec.md`, `decisions.md`, the PRD, `model.yaml`, a test's string. Once the agent
has asked the index — one of its MCP tools, which the guard is told about, or a query verb of `codegraph` through
the shell — its greps are its own business, and a search of another checkout is never this index's to answer.

**It reads the keel's contract and nothing else** (`docs/extensions.md`, *What a `before-search` guard is handed*):
one JSON object on stdin naming the tool, the pattern, where it looks and whose call it is. What that object does not
say the guard does not guess: handed no event at all — an older keel, which passes only the query — it cannot tell a
Glob from a Grep or one session from the next, and allows. It runs no command and opens no connection, reads the
index with two bounded queries, and allows wherever the index could not have answered: absent, unreadable, written
too long ago to trust, or with no route to the CLI on this machine. Whatever it allows for a reason like those, it
says on stderr.

Every route here runs the version the MCP server runs (`CODEGRAPH`), so two versions never write one database.
Standard library only, like every script the toolkit ships. Nothing here fails a command it hooks: a guard that
cannot decide allows the call.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def project_root(script: Path, depth: int) -> Path:
    """The repository root: the nearest directory above this script holding `project.json` (see models.py)."""
    for candidate in script.parents:
        if (candidate / "project.json").is_file():
            return candidate
    return script.parents[depth]


SCRIPT = Path(__file__).resolve()
ROOT = project_root(SCRIPT, 2)
# The one pin: the MCP server `./init --extension codegraph` writes, the repo-local `scripts/codegraph`, and every
# command below all run this release. `codegraph help` in it lists the query verbs INDEX_QUERY names.
CODEGRAPH = "@colbymchenry/codegraph@1.6.0"
DIRECTORY = ROOT / ".codegraph"
DATABASE = DIRECTORY / "codegraph.db"
ASIDE = DIRECTORY / "corrupt"
# Which session and delegate has asked the index, for `guard`: inside the index's own ignored directory.
ASKED = DIRECTORY / "asked.json"
EXTENSIONS = ROOT / ".slipwai/extensions.json"
# The gate, whose reading of index against tree `health` shares. Both ship with the extension now rather than
# with the toolkit — the keel carries no extension of its own — so this is a sibling path and not a walk up
# into the project's own `scripts/`, which is where this module used to live and no longer does.
GATE = SCRIPT.parent / "hooks/check.py"
# A command that asks the index something, as against one that maintains it (`sync`, `init`, `index`, `serve`).
INDEX_QUERY = re.compile(
    r"\bcodegraph(?:@[\w.-]+)?\s+(query|explore|context|node|files|callers|callees|impact|affected)\b")
# How long a sync or a rebuild may take before the step gives up and says so.
SYNC_SECONDS, BUILD_SECONDS = 120, 900
# How long a read of the database may wait on a lock, for the guard: it is in front of somebody's tool call.
READ_SECONDS = 1.0
# The words a refusal starts with, which is how the stream shows where `guard` refused a call.
REFUSED = "code-index: refused"
# The exit code that refuses, at a guard point and nowhere else (the keel's `guards.py`, `REFUSE`).
REFUSE = 2
# The version of the keel's search event this reads. A field added is the same version; a meaning changed is not.
EVENT_VERSION = 1
# The most of an event, and of the record of who asked, that is read. A shell command can be any length, and a
# guard that parsed megabytes in front of a tool call would be the thing its budget ends.
EVENT_BYTES, RECORD_BYTES = 1_000_000, 1_000_000
# How many askers the record keeps, newest first: sessions end and nothing tells this, so it is a window.
ASKED_KEPT = 200
# How many alternatives a pattern may name and still be a list of symbols rather than a regular expression.
ALTERNATIVES = 16
# How long since the index was last written before it is too old to hold anybody to. Not a measure of drift —
# that is the gate's, which hashes the tree and takes seconds — only the cheap sign that no client has been
# attached for weeks, when what the index would answer is about another codebase than the one being searched.
STALE_DAYS = 14
# The wrapper a refusal names, from the repository root: `scripts/` is three levels above this file.
# And this script, for the repair an allowed search is told about.
try:
    WRAPPER = (SCRIPT.parents[2] / "codegraph").relative_to(ROOT).as_posix()
    HEALTH = SCRIPT.relative_to(ROOT).as_posix()
except ValueError:
    WRAPPER, HEALTH = "scripts/codegraph", "scripts/extensions/codegraph/code_index.py"
SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
# Documents, whose words a text search is right for: a search confined to these is never a symbol search.
DOCUMENT = re.compile(r"(^|/)(docs|specs|\.specify)(/|$)|\.(md|mdx|txt|ya?ml|json|feature|csv|drawio|html)$")
IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
SHAPED = re.compile(r"[a-z0-9][A-Z]|[A-Za-z0-9]_[A-Za-z0-9]")


def adopted() -> bool:
    """An index is here, or the extension was elected and the index is due."""
    if DIRECTORY.is_dir():
        return True
    try:
        return "codegraph" in (json.loads(EXTENSIONS.read_text(encoding="utf-8")).get("extensions") or [])
    except (OSError, ValueError, AttributeError):
        return False


# Why a machine with Node can still have no `npx` on PATH: a hook's shell, and any non-interactive one, sources no
# profile, so a Node that nvm, volta or fnm put there is not found by name.
NO_ROUTE = ("neither `npx` nor `codegraph` is on PATH, nor under nvm, volta or fnm — a hook's or non-interactive "
            "shell sources no profile, so a Node one of those manages is found only where it keeps its versions")


def version_of(directory: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", directory.name)[:3])


def managed_node() -> Path | None:
    """The `bin/` holding `npx` of the newest Node that nvm, volta or fnm installed, or None where none did."""
    home = Path.home()
    nvm = Path(os.environ.get("NVM_DIR") or home / ".nvm") / "versions/node"
    fnm = [Path(os.environ["FNM_DIR"])] if os.environ.get("FNM_DIR") else []
    fnm += [home / ".local/share/fnm", home / "Library/Application Support/fnm", home / ".fnm"]
    candidates = sorted(nvm.glob("*/bin"), key=lambda found: version_of(found.parent), reverse=True)
    candidates.append(Path(os.environ.get("VOLTA_HOME") or home / ".volta") / "bin")
    for root in fnm:
        candidates += sorted((root / "node-versions").glob("*/installation/bin"),
                             key=lambda found: version_of(found.parent.parent), reverse=True)
    return next((found for found in candidates if (found / "npx").is_file()), None)


def route() -> list[str] | None:
    """How to run the pinned CLI: through `npx` where Node is, or an installed `codegraph` where it is not. A Node
    that nvm, volta or fnm manages counts: its `bin/` goes on this process's PATH, so `npx` finds its `node`."""
    if shutil.which("npx"):
        return ["npx", "-y", CODEGRAPH]
    if shutil.which("codegraph"):
        return ["codegraph"]
    found = managed_node()
    if found is None:
        return None
    os.environ["PATH"] = f"{found}{os.pathsep}{os.environ.get('PATH', '')}"
    return ["npx", "-y", CODEGRAPH]


def cli(*arguments: str, seconds: int = SYNC_SECONDS) -> tuple[bool, str]:
    command = route()
    if command is None:
        return False, NO_ROUTE
    try:
        done = subprocess.run([*command, *arguments], cwd=ROOT, text=True, capture_output=True, timeout=seconds,
                              stdin=subprocess.DEVNULL, env={**os.environ, "CODEGRAPH_NO_UPDATE_CHECK": "1"})
    except subprocess.TimeoutExpired:
        return False, f"`codegraph {' '.join(arguments)}` took longer than {seconds}s"
    except OSError as error:
        return False, str(error)
    said = (done.stdout + done.stderr).strip().splitlines()
    return done.returncode == 0, said[-1].strip("│└● ").strip() if said else ""


class Unopened(Exception):
    """The database could not be opened to be checked at all — which says nothing about whether it is sound."""


def damage() -> str | None:
    """Why the database cannot be trusted — SQLite's integrity check fails, or the file is not a database — or None.
    Raises `Unopened` when no read-only open succeeds: that is the environment, not the index.

    A WAL database left with no `-shm` beside it — how CodeGraph leaves one once its daemon exits — is refused by
    some SQLite builds on a plain read-only open (macOS's system Python: "unable to open database file"), and by any
    build where the directory is not writable. `immutable=1` reads it without the `-shm`, so the check tries that
    before it concludes anything; an open failure alone never has a sound database moved aside."""
    refused: list[str] = []
    for mode in ("mode=ro", "immutable=1"):
        try:
            with sqlite3.connect(f"{DATABASE.as_uri()}?{mode}", uri=True) as connection:
                verdict = connection.execute("PRAGMA integrity_check").fetchone()
            break
        except sqlite3.OperationalError as error:  # cannot open, cannot lock, read-only: no reading of the file
            refused.append(f"{mode}: {error}")
        except sqlite3.Error as error:  # the file was read, and it is not a sound database
            return str(error)
    else:
        raise Unopened("; ".join(refused))
    if verdict and verdict[0] == "ok":
        return None
    # SQLite reports every damaged cell on its own line; the first says what kind of damage, the count how much.
    lines = [line for line in str(verdict[0] if verdict else "no verdict").splitlines() if line.strip()
             and "in database main" not in line]
    return lines[0] + (f", and {len(lines) - 1} more" if len(lines) > 1 else "") if lines else "no verdict"


def gate() -> Any:
    """The extension's own `hooks/check.py`, loaded, for its reading of which files the index is behind on.

    None where the extension is not elected here: the index can still be asked and still be healthy, and a
    traceback about a missing gate would be this script failing over something it does not own.
    """
    import importlib.util
    if not GATE.is_file():
        return None
    sys.dont_write_bytecode = True  # no `__pycache__/` beside the gate in the project
    specification = importlib.util.spec_from_file_location("check_codegraph", GATE)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def behind() -> int | None:
    """How many tracked files the index has never seen or read before they changed; None where it cannot say."""
    reader = gate()
    found = reader.drift() if reader is not None else None
    return None if found is None else len(found[1]) + len(found[2])


def set_aside() -> str:
    """Move the database and its journal files under `.codegraph/corrupt/`, keeping only this latest copy."""
    shutil.rmtree(ASIDE, ignore_errors=True)
    ASIDE.mkdir(parents=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for suffix in ("", "-wal", "-shm", "-journal"):
        source = DATABASE.with_name(DATABASE.name + suffix)
        if source.exists():
            source.rename(ASIDE / f"{stamp}-{source.name}")
    return (ASIDE.relative_to(ROOT)).as_posix()


def checked() -> str | Unopened | None:
    """`damage()`, with an open failure returned rather than raised."""
    try:
        return damage()
    except Unopened as error:
        return error


def health() -> dict[str, Any]:
    """Make the index one an iteration can query, and say what that took: `current`, `synced`, `built`, `rebuilt`,
    `unreachable` (no route to the CLI) or `failed` (the step ran and the index is still not right). Nothing where
    no index was adopted."""
    if not adopted():
        return {}
    began = time.monotonic()
    result: dict[str, Any] = {}
    if route() is None:
        result = {"state": "unreachable", "detail": f"{NO_ROUTE}; so nothing can maintain or query the index"}
    elif not DATABASE.is_file():
        done, said = cli("init", "-y", ".", seconds=BUILD_SECONDS)
        result = {"state": "built", "detail": "there was no database; built it with `codegraph init`"}
        if not done:
            result = {"state": "failed", "detail": f"no database, and `codegraph init` failed: {said}"}
    elif isinstance(problem := checked(), Unopened):
        result = {"state": "failed", "detail": f"the database could not be opened to be checked ({problem}); left "
                                               "it where it is, since an open failure says nothing about the index"}
    elif problem is not None:
        where = set_aside()
        done, said = cli("init", "-y", ".", seconds=BUILD_SECONDS)
        result = {"state": "rebuilt", "detail": f"the database failed its integrity check ({problem}); moved it "
                                               f"to {where}/ and rebuilt it with `codegraph init`"}
        if not done:
            result = {"state": "failed", "detail": f"the database failed its integrity check ({problem}), was moved "
                                                   f"to {where}/, and `codegraph init` failed: {said}"}
    else:
        stale = behind()
        if stale:
            done, said = cli("sync", ".")
            result = {"state": "synced", "detail": f"{stale} tracked file(s) were ahead of the index; synced it"}
            if not done:
                result = {"state": "failed", "detail": f"{stale} tracked file(s) ahead of the index, and `codegraph "
                                                       f"sync` failed: {said}"}
        else:
            result = {"state": "current", "detail": "opens, passes its integrity check, and describes the tree"}
    if result["state"] in ("built", "rebuilt", "synced"):
        problem, stale = (checked() if DATABASE.is_file() else "no database was written"), None
        if problem is None:
            stale = behind()
        if problem is not None or stale:
            result = {"state": "failed", "detail": f"{result['detail']}, and it is still "
                      + (f"not sound ({problem})" if problem else f"behind on {stale} file(s)")}
    result["seconds"] = round(time.monotonic() - began, 1)
    return result


# --- which calls search the source for a symbol ---------------------------------------------------------------------


def symbols(names: list[str]) -> set[str]:
    """Which of these names the index holds a definition of."""
    if not names or not DATABASE.is_file():
        return set()
    marks = ",".join("?" * len(names))
    for mode in ("mode=ro", "immutable=1"):  # the second for a WAL database with no `-shm`, as `damage()` says
        try:
            connection = sqlite3.connect(f"{DATABASE.as_uri()}?{mode}", uri=True, timeout=READ_SECONDS)
            try:
                return {row[0] for row in connection.execute(
                    f"SELECT DISTINCT name FROM nodes WHERE kind NOT IN ('file', 'import') AND name IN ({marks})",
                    names)}
            finally:
                connection.close()
        except sqlite3.Error:
            continue
    return set()


def last_written() -> tuple[int, float | None]:
    """How many files the index holds and when it last indexed one, in seconds; raises where it cannot be read."""
    refused: sqlite3.Error | None = None
    for mode in ("mode=ro", "immutable=1"):
        try:
            connection = sqlite3.connect(f"{DATABASE.as_uri()}?{mode}", uri=True, timeout=READ_SECONDS)
            try:
                count, newest = connection.execute("SELECT COUNT(*), MAX(indexed_at) FROM files").fetchone()
            finally:
                connection.close()
            return int(count or 0), (float(newest) / 1000 if newest is not None else None)
        except sqlite3.Error as error:
            refused = error
    assert refused is not None
    raise refused


def unusable() -> str | None:
    """Why this index cannot be what a search is held to, or None. Offline, and two small reads at most."""
    if not DATABASE.is_file():
        return "there is no index here (`.codegraph/codegraph.db` is absent)"
    try:
        count, newest = last_written()
    except (sqlite3.Error, OSError, ValueError, TypeError) as error:
        return f"the index cannot be read ({type(error).__name__}: {error}); `python3 {HEALTH} health` repairs it"
    if not count or newest is None:
        return f"the index holds no file; `python3 {HEALTH} health` builds it"
    if time.time() - newest > STALE_DAYS * 86400:
        return (f"the index was last written on {time.strftime('%Y-%m-%d', time.localtime(newest))}, more than "
                f"{STALE_DAYS} days ago; `python3 {HEALTH} health` brings it up to date")
    if route() is None:
        return f"nothing here can ask the index: {NO_ROUTE}"
    return None


def symbol_of(pattern: str) -> str | None:
    """The pattern as the symbol(s) it names, or None where it is words: every alternative must be one identifier,
    and each must be shaped like a symbol or be a name the index defines."""
    if len(pattern) > 400:
        return None
    stripped = re.sub(r"\\[bB<>]|[\^$()]|\\\(|\\\)", "", pattern)
    parts = [part for part in re.split(r"\\?\|", stripped) if part]
    if not parts or len(parts) > ALTERNATIVES or not all(IDENTIFIER.fullmatch(part) for part in parts):
        return None
    known = symbols(parts)
    if all(SHAPED.search(part) or part in known for part in parts):
        return "|".join(parts)
    return None


def document(item: str) -> bool:
    return bool(DOCUMENT.search(item.rstrip("/*").replace("**", "")) or DOCUMENT.search(item))


def documents_only(paths: list[str], globs: list[str]) -> bool:
    """A search confined to documents: every path it names is one, or every file filter it carries is — `*.md`
    confines a search to documents wherever it starts. A filter that excludes (`!*.md`) confines it to nothing."""
    named = [item for item in paths if item]
    filters = [item for item in globs if item]
    if filters and all(not item.startswith("!") and document(item) for item in filters):
        return True
    return bool(named) and all(document(item) for item in named)


def commands_of(command: str) -> list[list[list[str]]]:
    """The command's pipelines, each a list of the words of its stages, split where the shell splits them: on `;`,
    `&&`, `||` and newlines between pipelines and on `|` between stages — never inside a quoted pattern."""
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    pipelines: list[list[list[str]]] = [[[]]]
    try:
        for token in lexer:
            if token in (";", "&&", "||", "&", ";;"):
                pipelines.append([[]])
            elif token == "|":
                pipelines[-1].append([])
            else:
                pipelines[-1][-1].append(token)
    except ValueError:
        return []
    return [[words for words in pipeline if words] for pipeline in pipelines if any(pipeline)]


def shell_searches(command: str) -> list[tuple[str, list[str], list[str], str]]:
    """Each search the command runs over files: its pattern, the paths it names, its include patterns and the
    directory it runs in — `.` until a `cd` moves it. A search reading another command's output — `git ls-files |
    grep Cue` — is over names, not source, and is not one."""
    found = []
    where = "."
    for pipeline in commands_of(command):
        first = pipeline[0] if pipeline else []
        if len(first) == 2 and first[0] in ("cd", "pushd"):
            where = str(Path(where) / os.path.expandvars(os.path.expanduser(first[1])))
            continue
        for position, words in enumerate(pipeline):
            while words and "=" in words[0] and not words[0].startswith("-"):
                words = words[1:]
            if not words:
                continue
            program = Path(words[0]).name
            if program == "git" and len(words) > 1 and words[1] == "grep":
                program, words = "grep", words[1:]
            if program not in SEARCHERS:
                continue
            pattern, paths, globs, rest = None, [], [], words[1:]
            index = 0
            while index < len(rest):
                word = rest[index]
                if word in ("-e", "--regexp") and index + 1 < len(rest):
                    pattern, index = rest[index + 1], index + 2
                    continue
                if word.startswith("--include=") or word.startswith("--glob="):
                    globs.append(word.split("=", 1)[1])
                elif word in ("-g", "--glob", "--include", "-t", "--type") and index + 1 < len(rest):
                    globs.append(rest[index + 1] if word not in ("-t", "--type") else f"*.{rest[index + 1]}")
                    index += 1
                elif word.startswith("-"):
                    pass
                elif pattern is None:
                    pattern = word
                else:
                    paths.append(word)
                index += 1
            if pattern is not None and (paths or position == 0):
                found.append((pattern, paths, globs, where))
    return found


def outside(cwd: str | None, where: str, paths: list[str]) -> bool:
    """Whether a search runs wholly outside this repository, so this index is not the one that could answer it.
    A session opened here can search another checkout — `cd ~/other && grep -rn version src` — and a name this
    repository happens to define is no reason to hold that search to an index of code it does not read."""
    base = Path(cwd) if cwd else ROOT
    targets = [base / where / os.path.expanduser(path) for path in paths] or [base / where]
    try:
        root = ROOT.resolve()
        return all(not target.resolve().is_relative_to(root) for target in targets)
    except (OSError, ValueError):
        return False


def symbol_search(tool: str, given: dict[str, Any], cwd: str | None = None) -> str | None:
    """The symbol a tool call searches this repository's source for, or None where it searches documents, words,
    nothing, or another directory than this repository. `cwd` is where the call runs, as the hook's event says."""
    if tool == "Grep":
        glob = given.get("glob") or (f"*.{given['type']}" if given.get("type") else "")
        path = str(given.get("path") or "")
        if documents_only([path], [str(glob)]) or outside(cwd, ".", [path] if path else []):
            return None
        return symbol_of(str(given.get("pattern", "")))
    if tool != "Glob" and given.get("command"):
        for pattern, paths, globs, where in shell_searches(str(given.get("command", ""))):
            if documents_only(paths, globs) or outside(cwd, where, paths):
                continue
            if symbol := symbol_of(pattern):
                return symbol
    return None


def index_query(tool: str, given: dict[str, Any]) -> bool:
    return tool.startswith(INDEX_TOOLS) or bool(INDEX_QUERY.search(str(given.get("command", ""))))


# --- the guard ------------------------------------------------------------------------------------------------------

# The index's own tools as a harness names them: what the manifest's guard declares it `sees`.
INDEX_TOOLS = "mcp__codegraph__"
# What an event names that this rule reads, each a string or absent. Anything else in it is not read.
READ = ("point", "tool", "pattern", "path", "glob", "type", "command", "cwd", "session", "agent")


def told() -> dict[str, Any] | None:
    """The event the keel wrote to stdin, or None where there is none: a terminal, nothing, or not one object."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        raw = sys.stdin.buffer.read(EVENT_BYTES + 1)
    except (OSError, ValueError):
        return None
    if len(raw) > EVENT_BYTES:
        return None
    try:
        read = json.loads(raw.decode("utf-8", "replace") or "null")
    except ValueError:
        return None
    return read if isinstance(read, dict) else None


def said(event: dict[str, Any]) -> dict[str, str]:
    """The fields this rule reads, where the event says them. A field that is absent, empty or not text is absent:
    the keel leaves out what a search did not name, and a value of another kind is not one it promised."""
    return {word: event[word] for word in READ if isinstance(event.get(word), str) and event[word].strip()}


def asker(event: dict[str, str]) -> str:
    """Whose call this is: the session, and the delegate inside it where there is one."""
    return f"{event['session']}:{event.get('agent') or 'host'}"


def load_asked() -> dict[str, float]:
    """Who has asked the index, and when. Anything but a sound record is nobody: a corrupt file, one that cannot
    be read, or one too large to be this script's is not evidence that anybody asked."""
    try:
        with ASKED.open("rb") as record:
            raw = record.read(RECORD_BYTES + 1)
        read = json.loads(raw.decode("utf-8")) if len(raw) <= RECORD_BYTES else None
    except (OSError, ValueError):
        return {}
    if not isinstance(read, dict):
        return {}
    return {who: float(when) for who, when in read.items()
            if isinstance(who, str) and isinstance(when, (int, float)) and not isinstance(when, bool)}


def record_asked(who: str) -> str | None:
    """Write down that `who` asked the index; why it could not be written, or None. Whole or not at all: the
    record is written beside itself and moved into place, so a guard ended half way leaves the last sound one."""
    if not DIRECTORY.is_dir():
        return "there is no `.codegraph/` here to keep the record in"
    asked = load_asked()
    asked[who] = time.time()
    kept = dict(sorted(asked.items(), key=lambda pair: pair[1])[-ASKED_KEPT:])
    written: str | None = None
    try:
        handle, written = tempfile.mkstemp(dir=DIRECTORY, prefix="asked.", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as record:
            record.write(json.dumps(kept) + "\n")
        os.replace(written, ASKED)
    except OSError as error:
        if written is not None:
            try:
                os.unlink(written)
            except OSError:
                pass
        return f"{type(error).__name__}: {error}"
    return None


def allowed(why: str) -> int:
    """Allow the call and say why, where the why is something a person would want to know."""
    print(f"code-index: allowed — {why}", file=sys.stderr)
    return 0


def noted(who: str) -> int:
    problem = record_asked(who)
    return allowed(f"this ask of the index could not be recorded ({problem}), so the next symbol search is "
                   "refused once more") if problem else 0


def guard() -> int:
    """Refuse a symbol search of the source from whoever has not asked the index yet; record who has.

    One script at two moments, as the keel's contract has it: told at `tool-use` that one of the index's own tools
    is being used, where what this exits with is discarded, and asked at `before-search` about one search. Returns
    `REFUSE` at the second and only there. Every other path returns 0, and says why where the reason is that it
    could not tell or that the index could not have answered."""
    event = told()
    if event is None:
        return allowed("cannot judge this search: the keel handed no event on stdin, so nothing says which tool "
                       "made it, where it looks or whose it is (a keel older than the one this guard was written "
                       "for hands only the query)")
    if event.get("v") != EVENT_VERSION:
        return allowed(f"cannot judge this search: the event's `v` is {event.get('v')!r}, and this guard reads "
                       f"version {EVENT_VERSION} of the keel's search event")
    given = said(event)
    point = given.get("point") or os.environ.get("SLIPWAI_POINT", "")
    if point == "tool-use":
        if not given.get("tool", "").startswith(INDEX_TOOLS):
            return 0
        if "session" not in given:
            return allowed("cannot record this ask: the event names no `session`, so nothing says whose it is")
        return noted(asker(given))
    if point != "before-search":
        return allowed(f"cannot judge: this guard answers at `before-search`, and was run at {point or 'no point'}")
    for needed, why in (("tool", "which tool made the search"), ("session", "whose search it is"),
                        ("cwd", "where the search runs")):
        if needed not in given:
            return allowed(f"cannot judge this search: the event names no `{needed}`, so nothing says {why}")
    tool = given["tool"]
    if "command" in given and index_query(tool, given):
        return noted(asker(given))
    symbol = symbol_search(tool, given, given["cwd"])
    if symbol is None:
        return 0
    if asker(given) in load_asked():
        return 0
    reason = unusable()
    if reason is not None:
        return allowed(reason)
    first = symbol.split("|")[0]
    print(f"{REFUSED} — `{symbol}` is a symbol, and this session has not asked the code index yet. Ask it first: "
          f"`{WRAPPER} callers {first}`, `{WRAPPER} impact {first}` or `{WRAPPER} explore {first}` "
          "(or the codegraph_explore tool).\nAfter that a symbol search is allowed; a search of documents "
          "(`specs/`, `docs/`, `*.md`), of words, or for a file by name always is.", file=sys.stderr)
    return REFUSE


def sync() -> int:
    """A delegate came back, having edited what it edited: bring the index up to it. Never fails the call."""
    if DATABASE.is_file() and route() is not None:
        cli("sync", ".")
    return 0


# --- what the stream says each delegate did --------------------------------------------------------------------------


def delegate_use(stream: Path, only: int | None = None) -> dict[int, list[dict[str, Any]]]:
    """Per iteration of a runner's stream, per agent — the host session, then each delegate in the order it was sent —
    how often it asked the index, which symbols it searched the source for before it had, and how often `guard`
    refused it. Claude Code marks a delegate's events with `parent_tool_use_id`; a harness whose stream does not
    is counted as the host alone."""
    found: dict[int, list[dict[str, Any]]] = {}
    if not stream.is_file():
        return found
    iteration, agents = 0, {}
    for line in stream.read_text(errors="replace", encoding="utf-8").splitlines():
        if line.startswith("# iteration "):
            iteration = int(line.split()[2])
            if only is not None and iteration != only:
                continue
            agents = {"": {"agent": "host", "queries": 0, "searched_first": [], "refused": 0}}
            found[iteration] = list(agents.values())
            continue
        if only is not None and iteration != only:
            continue
        try:
            happened = json.loads(line)
        except ValueError:
            continue
        if not isinstance(happened, dict) or iteration not in found:
            continue
        owner = agents.get(str(happened.get("parent_tool_use_id") or ""), agents[""])
        message = happened.get("message") if isinstance(happened.get("message"), dict) else {}
        for block in message.get("content") if isinstance(message.get("content"), list) else []:
            if not isinstance(block, dict):
                continue
            given = block.get("input") if isinstance(block.get("input"), dict) else {}
            if block.get("type") == "tool_use":
                name = str(block.get("name", ""))
                if name in ("Agent", "Task"):
                    agents[str(block.get("id", ""))] = {"agent": str(given.get("subagent_type") or "delegate"),
                                                        "queries": 0, "searched_first": [], "refused": 0}
                    found[iteration].append(agents[str(block.get("id", ""))])
                elif index_query(name, given):
                    owner["queries"] += 1
                elif not owner["queries"] and (symbol := symbol_search(name, given)):
                    owner["searched_first"].append(symbol)
            # An error result carrying the hook's words: an index answer quoting this file is not a refusal.
            elif block.get("type") == "tool_result" and block.get("is_error") and REFUSED in json.dumps(block.get("content")):
                owner["refused"] += 1
        item = happened.get("item") if isinstance(happened.get("item"), dict) else {}
        if happened.get("type") == "item.started":
            if (item.get("type") == "mcp_tool_call" and item.get("server") == "codegraph") or (
                    item.get("type") == "command_execution" and INDEX_QUERY.search(str(item.get("command", "")))):
                owner["queries"] += 1
            elif item.get("type") == "command_execution" and not owner["queries"]:
                symbol = symbol_search("Bash", {"command": item.get("command", "")})
                if symbol:
                    owner["searched_first"].append(symbol)
    return found


def use_lines(iteration: int, agents: list[dict[str, Any]]) -> list[str]:
    """The feed's and `status`'s account of one iteration: the queries per agent, then each agent that searched the
    source for a symbol before asking the index."""
    counts = ", ".join(f"{agent['agent']} {agent['queries']}" for agent in agents)
    lines = [f"cruise: iteration {iteration} asked the code index {sum(agent['queries'] for agent in agents)} time(s) — "
             f"{counts}"]
    for agent in agents:
        if agent["searched_first"]:
            shown = ", ".join(f"`{each}`" for each in dict.fromkeys(agent["searched_first"]))
            lines.append(f"cruise:   {agent['agent']} searched the source for {shown} before asking the index")
        if agent["refused"]:
            lines.append(f"cruise:   {agent['agent']} was refused {agent['refused']} symbol search(es) until it asked")
    return lines


def main(argv: list[str]) -> int:
    verb = argv[0] if argv else ""
    if verb == "health":
        said = health()
        print(f"code-index: {said['state']} — {said['detail']}" if said else "code-index: no index adopted here")
        return 1 if said.get("state") in ("failed", "unreachable") else 0
    if verb == "session":
        said = health()
        if said and said["state"] != "current":
            print(f"code-index: at session start the index was {said['state']} — {said['detail']}")
        return 0
    if verb == "guard":
        return guard()
    if verb == "sync":
        return sync()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
