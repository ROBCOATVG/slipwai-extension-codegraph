#!/usr/bin/env python3
"""`./init --extension codegraph`: install and index CodeGraph, and point the agent at it.

CodeGraph (https://github.com/colbymchenry/codegraph) is a local, 100%-offline MCP code-knowledge graph.
Its own installer already wires the MCP server into whichever coding agents it finds and appends its own
instruction block to their context files — but that config is the user's, on the one machine `./init` ran on,
and never reaches a container, a CI runner or the fresh session a `/cruise` iteration is. So this script does the
three things that belong to the project rather than to CodeGraph itself: index this repository, add one
marker-fenced pointer to `AGENTS.md` so the primary agent reaches for the graph on a cross-file question instead
of falling back to grep-and-read, and name the server in the committed project MCP file of every harness installed
here, so the connection travels with the checkout. The same block tells a delegated agent to probe its own session rather than assume it
inherited the primary agent's connection. The pointer says how to tell that an environment cannot reach
the index at all, because a checkout travels into
places its tooling does not, and the gate (`hooks/check.py`, which `make check-extensions` runs) is what notices
an index nothing is maintaining. It also writes `scripts/codegraph`, the wrapper the block names (`wrapper.py`),
before anything that needs the CLI: the wrapper reaches the index through `npx`, so it is owed wherever the
extension is elected, installed CLI or not.
See docs/extensions.md for what every extension's `init.py` owes.

`make agents` does not run this: the `project` point is `hooks/project.py`, which rewrites the block, writes the
wrapper where it is missing, and installs nothing.

Never fails `./init`: a missing `codegraph` CLI is reported, not fatal.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# This package's own directory, for `code_index`. It was the toolkit's own, under `agents/`, until
# slice 6.1c took every extension's parts out of the keel; the import kept pointing there, so `./init
# --extension codegraph` died at import with a ModuleNotFoundError before `main` could say anything — which
# conformance saw as two obligations broken, the exit and the AGENTS.md block that never got written.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from code_index import CODEGRAPH  # noqa: E402
from guidance import record_extension, replace_block, write_project_mcp  # noqa: E402
import wrapper  # noqa: E402

def project_root(script: Path, depth: int) -> Path:
    """The repository root: the nearest directory above this script holding `project.json`.

    This script's own tree is `<root>/scripts` in a generated project and `<root>/<layout.delivery>/scripts`
    where the method was installed beside an existing codebase (`project.json`'s `layout.delivery`), so how
    far below the root it sits is not something to count; `depth` is only the fallback for a tree with no
    manifest at all.
    """
    for candidate in script.parents:
        if (candidate / "project.json").is_file():
            return candidate
    return script.parents[depth]


ROOT = project_root(Path(__file__).resolve(), 3)

# Where `./init` actually is, from the repository root: beside this script's own tree at the root in a
# generated project, and under `layout.delivery` where the method was installed beside an existing codebase.
# Derived rather than written, because "run `./init --extension …`" is advice nobody can follow when the
# file is `./delivery/init` — the first real adoption to meet it typed `./init` four times.
DELIVERY = Path(__file__).resolve().parents[3]
INIT = "./init" if DELIVERY == ROOT else f"./{DELIVERY.relative_to(ROOT).as_posix()}/init"
MARKER_BEGIN = "<!-- extension:codegraph:begin -->"
MARKER_END = "<!-- extension:codegraph:end -->"
# The paths the block names, from the repository root: under `scripts/` at the root in a generated project, and
# under `layout.delivery` beside an existing codebase. Every one is a file this package ships or `main` writes —
# `tests/test_package.py` runs `./init` in a scratch project and looks for each — because 1.0.0 named a wrapper
# nothing wrote and a gate by the name the keel's version 1 gave it, and a delegate that followed the page ran a
# file that was not there.
SCRIPTS = "scripts" if DELIVERY == ROOT else f"{DELIVERY.relative_to(ROOT).as_posix()}/scripts"
WRAPPER = f"{SCRIPTS}/codegraph"
PACKAGE = f"{SCRIPTS}/extensions/codegraph"
GUARD = f"{PACKAGE}/guards/ask_the_index.py"
AGREE = f"python3 {SCRIPTS}/extensions/guards.py --elect codegraph"


def guards_held() -> dict[str, list[str]]:
    """Per harness installed here, the moments a guard holds at: what the keel hands a hook as
    `SLIPWAI_GUARDS_HELD` at `init` and `project`, and what its `guard_harness.py --held` prints.

    Both, because this module is read twice: run as a hook, with the variable, and imported by the drift check,
    without it. They are one function of the project's files, so the block is the same either way. A keel that
    has neither — one older than slipwai #121 — tells an extension nothing, and the answer is that nothing holds:
    under it the guard is handed no search to judge and allows every one."""
    try:
        told = json.loads(os.environ["SLIPWAI_GUARDS_HELD"])
    except (KeyError, ValueError):
        try:
            import guard_harness  # the toolkit's, beside `guidance` in `scripts/extensions/`
            told = guard_harness.held()
        except Exception:  # noqa: BLE001 — a keel without it, or a registry it cannot read: told nothing
            told = {}
    if not isinstance(told, dict):
        return {}
    return {key: [moment for moment in moments if isinstance(moment, str)]
            for key, moments in told.items() if isinstance(key, str) and isinstance(moments, list)}


def guard_agreed() -> bool:
    """Whether a person has agreed to this extension's `before-search` guard here. Read, and never written: the
    registry is the agreement, and `AGREE` is the command that gives one."""
    try:
        registry = json.loads((ROOT / ".slipwai/guards.json").read_text(encoding="utf-8"))
        return any(isinstance(body, dict) and body.get("extension") == "codegraph"
                   for body in registry["guards"]["before-search"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def harness_names() -> dict[str, str]:
    """Each harness's own name, for a sentence a person reads: `Claude Code` and not `claude`."""
    try:
        registry = json.loads((DELIVERY / "scripts/agents/registry.json").read_text(encoding="utf-8"))
        return {row["key"]: row["name"] for row in registry["harnesses"]
                if isinstance(row.get("key"), str) and isinstance(row.get("name"), str)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def what_holds_the_rule() -> str:
    """The sentences that say what makes a session ask the index first — per harness, and only what is so.

    A guard holds on a harness where the keel can run one before a search there **and** a person has agreed to
    it. Where it could and nobody has, nothing refuses and the command that agrees is named. Where the harness
    has no such moment, nothing can, and agreeing would change nothing there. 1.0.0 promised a hook on every
    harness and 1.0.1 promised none; this says which it is, here."""
    held, names = guards_held(), harness_names()
    holding = sorted(names.get(key, key) for key, moments in held.items() if "before-search" in moments)
    unseen = sorted(names.get(key, key) for key, moments in held.items()
                    if "before-search" in moments and "tool-use" not in moments)
    without = sorted(names.get(key, key) for key, moments in held.items() if "before-search" not in moments)
    said: list[str] = []
    if holding and guard_agreed():
        said.append(
            f"In {listed(holding)}, a guard this project agreed to (`{GUARD}`, at the keel's `before-search` "
            "point) refuses a search of the source for a symbol — a Grep, or `grep`, `rg`, `ag`, `ack` or "
            "`git grep` through the shell — from a session or a delegate that has not asked the index yet, and "
            f"names the commands above. Once it has asked, through `{WRAPPER}` or over MCP, its searches are its "
            "own. It never refuses a search of documents (`specs/`, `docs/`, `*.md`), of words, or for a file by "
            "name, and it refuses nothing where the index is missing, unreadable or weeks unwritten.")
        if unseen:
            said.append(f"In {listed(unseen)} an ask over MCP is not shown to the guard, so ask once through "
                        f"`{WRAPPER}`.")
    elif holding:
        said.append(
            f"In {listed(holding)}, a guard can refuse a search of the source for a symbol until the session has "
            "asked the index, but nobody has agreed to it here, so nothing refuses a search and asking the index "
            f"first is the session's own to do. `{AGREE}` agrees to it, and `make agents` then rewrites this "
            "paragraph.")
    if without:
        said.append(f"In {listed(without)}, nothing can refuse a search: the keel has no moment before one "
                    "there, so asking the index first is the session's own to do.")
    if not said:
        said.append("No guard holds this here — asking the index first is the session's own to do.")
    return "**What holds asking first.** " + " ".join(said)


GUIDANCE = f"""
{MARKER_BEGIN}
## CodeGraph
This project is indexed by CodeGraph (`.codegraph/`). **The index answers symbol questions; text search answers
questions about words.** Who calls a function, what it calls, where a type is used, what a change would reach:
ask the index first —

    {WRAPPER} callers <symbol>        {WRAPPER} impact <symbol>
    {WRAPPER} explore <names or a question>

`{WRAPPER}` runs the pinned CLI through `npx`, or an installed `codegraph`, so it answers in every session
with a shell — a delegate's included — whatever MCP tools that session was given; `codegraph_explore` over MCP is
the same index where your tools list it. A search of `spec.md`, `decisions.md`, the PRD, `model.yaml` or a test's
string literal ("done for the day") is a text search, and grep is right for it; locating a file by name is a
`find`, not a question for the index. Say which route you used when you report what you found.

**What keeps the index sound.** This extension's `after-stage` hook (`{PACKAGE}/hooks/sync.py`) syncs the index
after each rung a `/cruise` captain runs, so the next rung asks an index that has read what the last one wrote; it
never fails a rung, and says so where it could not sync. `python3 {PACKAGE}/code_index.py health` opens the
database, integrity-checks it, moves a corrupt one aside and rebuilds it (it is derived from the source and ignored
by Git), and syncs a stale one: the repair by hand, and the step to take at the start of a session nothing has
synced for.

{what_holds_the_rule()}

**The connection travels with the checkout.** The project-scoped MCP file of every harness installed here
names the server, started through `npx` at the same pinned version: `.mcp.json` for Claude Code (with
`alwaysLoad`, so its tool is loaded at session start rather than behind the tool-search step), `.codex/config.toml`
for Codex, `.gemini/settings.json` for Gemini CLI, `.cursor/mcp.json` for Cursor, `opencode.json` for opencode.
Where a harness still lists `codegraph_explore` as a bare name with no schema, it is not loaded yet rather than
unavailable — load it by name through that harness's tool-search step, or use `{WRAPPER}`.

**It is only current while a client is attached.** CodeGraph's watcher runs in a daemon that starts with an MCP
client or a `codegraph` command, shuts down on an idle timeout, and turns itself off where CodeGraph decides it
is sandboxed — so the syncs above do the keeping, and `make check-extensions`, part of `make verify`, runs this
extension's gate (`{PACKAGE}/hooks/check.py`), which rebuilds a corrupt database, syncs a stale one, and fails
with the date it was last written where the index still cannot be made sound and current. A corrupt database is
the one CodeGraph's own `status` and `sync` call up to date.

**A sub-agent does not inherit this session's connection**, and needs none: `{WRAPPER}` is in its shell.
Do not pass the parent conversation merely to carry that fact — every harness receives this `AGENTS.md` block,
while a delegate keeps its focused stage brief. `commands/sail.md`, *Who runs each stage*, carries the same
boundary.

**Where no route exists** — no Node and no `codegraph` — `{WRAPPER}` says so; then say in as many words
that the answer is a text search ("the database is here, the tooling is not"), and work as a project with no
index would. Install Node, or the CLI
(`curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh`), and re-adopt with
`{INIT} --extension codegraph`.
{MARKER_END}
"""


# The server, started through `npx` rather than the `codegraph` binary because the file it goes into is committed
# and travels: a checkout with Node reaches the index whether or not the CLI was installed there — a container, a
# sandbox, a CI runner, the cases the block above describes. Written into the project MCP file of every harness
# installed here (`scripts/agents/registry.json`, `projectMcp`; `guidance.write_project_mcp`). Proved 2026-09-22:
# a Claude Code 2.1.280 print session given `.mcp.json` with `--mcp-config` connected this server and answered a
# caller question through `codegraph_explore`.
# Pinned to the release every other route runs (`code_index.py`, `CODEGRAPH`), so the server and the CLI never
# write one database from two versions of its schema.
MCP_COMMAND = ["npx", "-y", CODEGRAPH, "serve", "--mcp"]


def project_guidance() -> None:
    """Record this election and make its factory-owned projections current: the guidance block, and the MCP file
    each installed harness reads. Installation and indexing are `main`'s alone."""
    record_extension("codegraph")
    replace_block("codegraph", GUIDANCE)
    for line in write_project_mcp("codegraph", MCP_COMMAND):
        print(f"codegraph: {line}")


def main() -> int:
    # First, and whatever follows: the wrapper needs Node rather than the CLI, and the block that names it may
    # already be in `AGENTS.md` from an earlier election.
    problem = wrapper.write()
    if problem:
        print(f"codegraph: {problem}", file=sys.stderr)
    if shutil.which("codegraph") is None:
        # Naming the recovery matters more than naming the tool: without the second command this project
        # keeps no pointer to CodeGraph, so a reader who installs the CLI and stops there ends up with a
        # working index no agent is ever told about.
        print(
            "CodeGraph CLI not found: nothing was indexed and AGENTS.md is unchanged.\n"
            "Install it:\n"
            "  curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh\n"
            "Then adopt it here, which is what points the agent at it:\n"
            f"  {INIT} --extension codegraph",
            file=sys.stderr,
        )
        return 0
    # `check=False`: an extension may not fail `./init` (docs/extensions.md), and a raised
    # CalledProcessError here would also skip the pointer below — leaving exactly the half-adopted state
    # the missing-CLI branch takes care to avoid.
    installed = subprocess.run(["codegraph", "install", "--yes", "--init"], cwd=ROOT, check=False)
    if installed.returncode != 0:
        print(
            f"`codegraph install` exited {installed.returncode}: AGENTS.md is unchanged.\n"
            "Fix what it reported, then adopt it here:\n"
            f"  {INIT} --extension codegraph",
            file=sys.stderr,
        )
        return 0
    project_guidance()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
