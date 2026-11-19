#!/usr/bin/env python3
"""What this package promises a project, run in a scratch project rather than read off the page.

1.0.0 named a command it did not ship, declared a hook file it lacked, and left `make agents` unable to
rewrite its own block. Each was a sentence nothing held to a file, so each test here builds a project the
way the keel's conformance suite does — `project.json`, an `AGENTS.md` with a person's paragraph, the
toolkit's `scripts/` and this package's files under `scripts/extensions/codegraph/` — and fires the points
through the toolkit's own `hooks.py`, which is the only way a hook runs in a real project.

    python -m unittest discover -s tests -v

The toolkit comes from an installed slipwai (`slipwai.assets.TOOLKIT_ROOT`), or from `SLIPWAI_TOOLKIT`
where the interpreter running the tests is not the one slipwai is installed for. With neither, the tests
that need a project are skipped and say so; the ones about what the package ships still run.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parents[1]
KEY = "codegraph"
PERSONS_WORDS = "This paragraph was written by a person and no install may take it away.\n"
# A path under the project's `scripts/` or `commands/`, as a page names one.
NAMED = re.compile(r"(?<![\w./<>{}-])((?:scripts|commands)/[A-Za-z0-9_./-]*[A-Za-z0-9_])")


def toolkit() -> Path | None:
    given = os.environ.get("SLIPWAI_TOOLKIT")
    if given:
        return Path(given)
    try:
        from slipwai.assets import TOOLKIT_ROOT
    except ImportError:
        return None
    return Path(TOOLKIT_ROOT)


TOOLKIT = toolkit()
needs_toolkit = unittest.skipIf(
    TOOLKIT is None, "no slipwai toolkit: install slipwai for this interpreter, or set SLIPWAI_TOOLKIT")


# The keel that hands a `before-search` guard the search and tells it when its own tools are used (slipwai #121).
# An older toolkit has neither script, the guard can refuse nothing under it, and the tests of the rule say so.
GUARD_KEEL = TOOLKIT is not None and all((TOOLKIT / "scripts" / part).is_file() for part in (
    "agents/tool_event.py", "extensions/guard_harness.py", "extensions/guard_offer.py"))
needs_guard_keel = unittest.skipUnless(
    GUARD_KEEL, "this slipwai toolkit hands a guard no search event (it is older than slipwai #121), so the "
                "guard allows every search under it and there is no rule to test")


def manifest() -> dict:
    return json.loads((PACKAGE / "extension.json").read_text(encoding="utf-8"))


def declared() -> dict[str, dict]:
    """The manifest's hooks in the long form the keel resolves them to."""
    return {name: ({"run": body} if isinstance(body, str) else dict(body))
            for name, body in manifest().get("hooks", {}).items()}


def declared_guards() -> dict[str, dict]:
    """The manifest's guards, as the keel writes them beside the others' in `available-guards.json`."""
    return {name: ({"run": body, "budget": "5s"} if isinstance(body, str) else dict(body))
            for name, body in manifest().get("guards", {}).items()}


def package_files() -> list[Path]:
    """What the keel copies into a project: every file but the manifest (`extension_directory.files`)."""
    return sorted(path.relative_to(PACKAGE) for path in PACKAGE.rglob("*")
                  if path.is_file() and path.name != "extension.json" and ".git" not in path.parts
                  and "__pycache__" not in path.parts)


class Project:
    """A scratch project with this extension's files where `./init` would find them, and `codegraph` elected."""

    def __init__(self, area: Path) -> None:
        assert TOOLKIT is not None
        self.root = area / "project"
        self.place = self.root / "scripts/extensions" / KEY
        self.place.mkdir(parents=True)
        for shared in sorted((TOOLKIT / "scripts").rglob("*")):
            if shared.is_file() and "__pycache__" not in shared.parts:
                target = self.root / "scripts" / shared.relative_to(TOOLKIT / "scripts")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(shared.read_bytes())
        if (TOOLKIT / "commands").is_dir():
            shutil.copytree(TOOLKIT / "commands", self.root / "commands")
        for relative in package_files():
            target = self.place / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # Bytes and no mode, as the keel copies them: nothing in a project is executable by inheritance.
            target.write_bytes((PACKAGE / relative).read_bytes())
        (self.root / "project.json").write_text("{}\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text(f"# A project\n\n{PERSONS_WORDS}", encoding="utf-8")
        (self.root / "scripts/extensions/available.json").write_text(
            json.dumps({KEY: declared()}), encoding="utf-8")
        (self.root / "scripts/extensions/available-guards.json").write_text(
            json.dumps({KEY: declared_guards()}), encoding="utf-8")
        # The harness `./init` is installing, as the keel names it to a hook. A test changes it to stand somewhere
        # no guard holds.
        self.harness = "claude"
        # A home with no nvm, volta or fnm in it, and a `bin/` a test may put a stand-in `codegraph` on.
        self.home = area / "home"
        self.bin = area / "bin"
        self.calls = area / "calls"
        self.home.mkdir()
        self.bin.mkdir()
        elected = self.run("scripts/extensions/hooks.py", "--elect", KEY)
        assert elected.returncode == 0, elected.stderr

    def environment(self, tool: bool) -> dict[str, str]:
        kept = {name: value for name, value in os.environ.items()
                if name not in ("NVM_DIR", "VOLTA_HOME", "FNM_DIR") and not name.startswith("SLIPWAI_")}
        return {**kept, "HOME": str(self.home), "PATH": str(self.bin) if tool else "",
                "SLIPWAI_INTEGRATION": self.harness}

    def stand_in(self, body: str = "") -> None:
        """A `codegraph` that records how it was called and from where, in place of the real one."""
        script = self.bin / "codegraph"
        script.write_text(f"#!/bin/sh\necho \"$PWD|$*\" >> '{self.calls}'\n{body}\n", encoding="utf-8")
        script.chmod(0o755)

    def called(self) -> list[str]:
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.is_file() else []

    def run(self, script: str, *arguments: str, tool: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.root / script), *arguments], cwd=self.root,
                              capture_output=True, text=True, timeout=120, env=self.environment(tool))

    def fire(self, point: str, *arguments: str, tool: bool = False) -> subprocess.CompletedProcess:
        return self.run("scripts/extensions/hooks.py", point, *arguments, tool=tool)

    def init(self, tool: bool = True) -> subprocess.CompletedProcess:
        return self.run(f"scripts/extensions/{KEY}/init.py", tool=tool)

    def snapshot(self) -> dict[str, tuple[int, bytes]]:
        return {path.relative_to(self.root).as_posix(): (stat.S_IMODE(path.stat().st_mode), path.read_bytes())
                for path in sorted(self.root.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}

    def agents(self) -> str:
        return (self.root / "AGENTS.md").read_text(encoding="utf-8")

    def module(self, relative: str):
        """One of the project's copies of this package's scripts, loaded from where it sits."""
        path = self.place / relative
        specification = importlib.util.spec_from_file_location(f"scratch_{path.stem}_{id(self)}", path)
        assert specification is not None and specification.loader is not None
        loaded = importlib.util.module_from_spec(specification)
        before = list(sys.path)
        try:
            specification.loader.exec_module(loaded)
        finally:
            sys.path[:] = before
            for name in ("guidance", "guard_harness", "code_index", "init", "wrapper"):
                sys.modules.pop(name, None)
        return loaded

    def canonical(self) -> str:
        """`GUIDANCE` as this project's own scripts read it: it says what holds the rule *here*, so it is read
        where a hook and the drift check read it, in the project's environment, and not in this process's."""
        read = subprocess.run(
            [sys.executable, "-c", "import sys; sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1]); "
                                   "import init; sys.stdout.write(init.GUIDANCE)", str(self.place)],
            cwd=self.root, capture_output=True, text=True, timeout=120, env=self.environment(False))
        assert read.returncode == 0, read.stderr
        return read.stdout.strip("\n")

    # --- what the guard meets -------------------------------------------------------------------------------

    def index(self, *names: str, written: float | None = None) -> Path:
        """A `.codegraph/codegraph.db` holding a definition of each name, last written `written` (now)."""
        database = self.root / ".codegraph/codegraph.db"
        database.parent.mkdir(exist_ok=True)
        database.unlink(missing_ok=True)
        moment = int((time.time() if written is None else written) * 1000)
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL)")
            connection.execute("CREATE TABLE files (path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, "
                               "indexed_at INTEGER NOT NULL)")
            connection.executemany("INSERT INTO nodes VALUES (?, 'function', ?)",
                                   [(f"n{position}", name) for position, name in enumerate(names)])
            connection.execute("INSERT INTO files VALUES ('apps/orders.py', 'x', ?)", (moment,))
        connection.close()
        return database

    def agree(self) -> None:
        """A person's yes, given the way the keel names: nothing in this package writes it."""
        done = self.run("scripts/extensions/guards.py", "--elect", KEY)
        assert done.returncode == 0, done.stderr

    def session(self, verb: str, event: dict, tool: bool = True) -> subprocess.CompletedProcess:
        """`scripts/agents/session.py <verb>`, the way a harness runs it: its own event on stdin."""
        return subprocess.run([sys.executable, str(self.root / "scripts/agents/session.py"), verb],
                              input=json.dumps(event), capture_output=True, text=True, cwd=self.root,
                              timeout=120, env=self.environment(tool))

    def harness_event(self, tool_name: str, session: str = "s-1", agent: str = "", **given: str) -> dict:
        event = {"session_id": session, "cwd": str(self.root), "hook_event_name": "PreToolUse",
                 "tool_name": tool_name, "tool_input": given}
        return {**event, "agent_id": agent} if agent else event

    def grep(self, pattern: str = "place_order", session: str = "s-1", agent: str = "",
             **searched: str) -> subprocess.CompletedProcess:
        return self.session("before-search", self.harness_event("Grep", session, agent, pattern=pattern, **searched))

    def shell(self, command: str, session: str = "s-1", agent: str = "") -> subprocess.CompletedProcess:
        return self.session("before-search", self.harness_event("Bash", session, agent, command=command))

    def asks_over_mcp(self, session: str = "s-1", agent: str = "") -> subprocess.CompletedProcess:
        return self.session("tool-use", self.harness_event("mcp__codegraph__codegraph_explore", session, agent,
                                                           query="who calls place_order"))

    def guard(self, told: str | None, tool: bool = True, **named: str) -> subprocess.CompletedProcess:
        """The guard's own script, run as the keel's runner runs it but with whatever stdin a test hands it."""
        script = self.place / declared_guards()["before-search"]["run"]
        return subprocess.run([sys.executable, str(script)], input=told, capture_output=True, text=True,
                              cwd=self.root, timeout=120, env={**self.environment(tool), **named},
                              stdin=subprocess.DEVNULL if told is None else None)

    def searched(self, tool: str = "Grep", **fields: str) -> dict:
        """A search as the keel's contract hands one to a guard: `docs/extensions.md`, the search event."""
        return {"v": 1, "point": "before-search", "tool": tool, "cwd": str(self.root), "session": "s-1", **fields}

    def asked(self) -> Path:
        return self.root / ".codegraph/asked.json"


class ScratchProject(unittest.TestCase):
    def setUp(self) -> None:
        area = tempfile.TemporaryDirectory()
        self.addCleanup(area.cleanup)
        self.project = Project(Path(area.name).resolve())


class WhatThePackageShips(unittest.TestCase):
    def test_every_declared_hook_is_a_file_the_package_ships(self) -> None:
        for point, body in declared().items():
            with self.subTest(point=point):
                self.assertTrue((PACKAGE / body["run"]).is_file(),
                                f"extension.json declares `{point}` as {body['run']}, which is not in the package")

    def test_the_project_point_is_not_the_entry_point(self) -> None:
        # Undeclared, `project` defaults to `init.py`, which installs: a re-projection is not an election.
        self.assertIn("project", declared())
        self.assertNotEqual(declared()["project"]["run"], declared()["init"]["run"])

    def test_the_stage_hook_keeps_inside_the_budget_it_declares(self) -> None:
        body = declared()["after-stage"]
        self.assertEqual(body.get("budget"), "30s")
        source = (PACKAGE / body["run"]).read_text(encoding="utf-8")
        seconds = int(re.search(r"^SECONDS = (\d+)$", source, re.MULTILINE).group(1))
        self.assertLess(seconds, 30)

    def test_the_version_is_the_changelogs_newest_entry(self) -> None:
        version = (PACKAGE / "VERSION").read_text(encoding="utf-8").strip()
        newest = re.search(r"(?m)^## (\S+)", (PACKAGE / "CHANGELOG.md").read_text(encoding="utf-8")).group(1)
        self.assertEqual(version, newest)


@needs_toolkit
class TheGuidanceNamesWhatIsThere(ScratchProject):
    def test_every_path_the_block_names_is_in_an_adopted_project(self) -> None:
        self.project.stand_in()
        self.assertEqual(self.project.init().returncode, 0)
        named = sorted(set(NAMED.findall(self.project.canonical())))
        self.assertIn("scripts/codegraph", named)
        for path in named:
            with self.subTest(path=path):
                self.assertTrue((self.project.root / path).exists(), f"the block names {path}, which is not here")

    def test_every_path_the_scripts_name_is_in_an_adopted_project(self) -> None:
        self.project.stand_in()
        self.assertEqual(self.project.init().returncode, 0)
        for relative in package_files():
            if relative.suffix != ".py" and relative.as_posix() != "bin/codegraph" or relative.parts[0] == "tests":
                continue
            for path in sorted(set(NAMED.findall((PACKAGE / relative).read_text(encoding="utf-8")))):
                with self.subTest(file=relative.as_posix(), path=path):
                    self.assertTrue((self.project.root / path).exists(),
                                    f"{relative} names {path}, which is not in a project that adopted this")

    def test_the_gate_is_called_by_the_name_it_runs_under(self) -> None:
        block = self.project.canonical()
        self.assertNotIn("check-codegraph", block)
        self.assertIn("`make check-extensions`", block)
        for gone in ("/drive", "drive.md"):
            self.assertNotIn(gone, block)


@needs_toolkit
class TheWrapper(ScratchProject):
    def test_init_writes_it_executable_and_a_second_run_changes_nothing(self) -> None:
        self.project.stand_in()
        first = self.project.init()
        self.assertEqual(first.returncode, 0, first.stderr)
        wrapper = self.project.root / "scripts/codegraph"
        self.assertTrue(wrapper.is_file())
        self.assertTrue(os.access(wrapper, os.X_OK))
        once = self.project.snapshot()
        self.assertEqual(self.project.init().returncode, 0)
        self.assertEqual(once, self.project.snapshot())

    def test_init_writes_it_where_the_cli_is_not_installed(self) -> None:
        # The wrapper reaches the index through `npx`, so the machine `./init` ran on needs no `codegraph`.
        run = self.project.init(tool=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(os.access(self.project.root / "scripts/codegraph", os.X_OK))

    def test_a_file_somebody_else_put_there_is_left_and_said(self) -> None:
        theirs = self.project.root / "scripts/codegraph"
        theirs.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        self.project.stand_in()
        run = self.project.init()
        self.assertEqual(run.returncode, 0)
        self.assertEqual(theirs.read_text(encoding="utf-8"), "#!/bin/sh\necho mine\n")
        self.assertIn("scripts/codegraph", run.stderr)
        self.assertRegex(run.stderr, r"`[^`]+`")

    def test_it_passes_its_arguments_to_the_cli_from_the_project_root(self) -> None:
        self.project.stand_in()
        self.project.init()
        self.project.calls.unlink()
        elsewhere = self.project.root / "scripts/agents"
        run = subprocess.run([str(self.project.root / "scripts/codegraph"), "callers", "decideCue"], cwd=elsewhere,
                             capture_output=True, text=True, timeout=60,
                             env={**self.project.environment(True),
                                  "PATH": f"{self.project.bin}{os.pathsep}{Path(sys.executable).parent}"
                                          f"{os.pathsep}/usr/bin{os.pathsep}/bin"} | self.without_npx())
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.project.called(), [f"{self.project.root}|callers decideCue"])

    def without_npx(self) -> dict[str, str]:
        """Skip where this machine has an `npx` beside its Python or in `/usr/bin`: the route would be the real CLI."""
        for directory in (Path(sys.executable).parent, Path("/usr/bin"), Path("/bin")):
            if (directory / "npx").exists():
                self.skipTest(f"{directory}/npx would be run instead of the stand-in")
        return {}

    def test_it_says_so_where_no_route_exists(self) -> None:
        self.project.init(tool=False)
        run = self.project.run("scripts/codegraph", "callers", "decideCue")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("scripts/codegraph:", run.stderr)
        self.assertIn("text search", run.stderr)


@needs_toolkit
class TheProjectHook(ScratchProject):
    def adopted(self) -> None:
        self.project.stand_in()
        self.assertEqual(self.project.init().returncode, 0)
        self.project.calls.unlink()

    def test_it_rewrites_a_drifted_block_and_nothing_else(self) -> None:
        self.adopted()
        agents = self.project.root / "AGENTS.md"
        canonical = self.project.canonical()
        agents.write_text(self.project.agents().replace("## CodeGraph", "## CodeGraph, as somebody edited it"),
                          encoding="utf-8")
        self.assertNotIn(canonical, self.project.agents())
        before = self.project.snapshot()
        run = self.project.fire("project", tool=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stderr, "")
        self.assertIn(canonical, self.project.agents())
        self.assertIn(PERSONS_WORDS, self.project.agents())
        after = self.project.snapshot()
        self.assertEqual({name for name in set(before) | set(after) if before.get(name) != after.get(name)},
                         {"AGENTS.md"})
        self.assertEqual(self.project.called(), [], "a re-projection ran the CLI")

    def test_a_second_run_changes_nothing(self) -> None:
        self.adopted()
        self.project.fire("project", tool=True)
        once = self.project.snapshot()
        self.project.fire("project", tool=True)
        self.assertEqual(once, self.project.snapshot())

    def test_the_drift_check_passes_after_it(self) -> None:
        self.adopted()
        agents = self.project.root / "AGENTS.md"
        agents.write_text(self.project.agents().replace("ask the index first", "ask whoever"), encoding="utf-8")
        self.assertEqual(self.project.run("scripts/extensions/project.py", "--check").returncode, 1)
        self.project.fire("project")
        check = self.project.run("scripts/extensions/project.py", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_it_installs_nothing_where_the_project_never_ran_init(self) -> None:
        self.project.stand_in()
        run = self.project.fire("project", tool=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(self.project.called(), [], "a re-projection ran the CLI")
        self.assertFalse((self.project.root / ".codegraph").exists())

    def test_a_project_that_elected_1_0_0_is_green_after_it_with_no_command_run_by_anyone(self) -> None:
        """What an upgrade is: the package's files replaced, `make agents` or `slipwai migrate` firing this point,
        and then the gate. 1.0.0 wrote no wrapper, so the gate would refuse the project it had just upgraded."""
        wrapper = self.project.root / "scripts/codegraph"
        self.assertFalse(wrapper.exists())
        self.assertEqual(self.project.fire("check", "--fatal").returncode, 1, "the state an upgrade starts from")
        self.project.stand_in()
        run = self.project.fire("project", tool=True)
        self.assertEqual(run.returncode, 0)
        self.assertIn("scripts/codegraph", run.stdout)
        self.assertTrue(os.access(wrapper, os.X_OK))
        self.assertEqual(self.project.called(), [], "writing the wrapper ran the CLI")
        self.assertIn(self.project.canonical(), self.project.agents())
        gate = self.project.fire("check", "--fatal")
        self.assertEqual(gate.returncode, 0, gate.stderr)

    def test_it_leaves_somebody_elses_file_at_that_path_and_says_so(self) -> None:
        theirs = self.project.root / "scripts/codegraph"
        theirs.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        run = self.project.fire("project")
        self.assertEqual(run.returncode, 0, "a hook reports; it never fails what fired it")
        self.assertEqual(theirs.read_text(encoding="utf-8"), "#!/bin/sh\necho mine\n")
        self.assertIn("left alone", run.stdout + run.stderr)


@needs_toolkit
class TheStageHook(ScratchProject):
    def index(self) -> None:
        (self.project.root / ".codegraph").mkdir()
        (self.project.root / ".codegraph/codegraph.db").write_bytes(b"")

    def test_it_syncs_the_index_after_a_rung(self) -> None:
        self.index()
        self.project.stand_in()
        run = self.project.fire("after-stage", "--stage", "drive", "--slice", "s1", tool=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stderr, "")
        self.assertEqual(self.project.called(), [f"{self.project.root}|sync ."])
        self.assertIn("codegraph: synced", run.stdout)

    def test_it_says_what_it_could_not_do_and_still_exits_0(self) -> None:
        self.index()
        for name, body, tool, expected in (
                ("no route", "", False, "neither `npx` nor `codegraph`"),
                ("a failed sync", "echo 'database is locked'; exit 3", True, "database is locked")):
            with self.subTest(name):
                if tool:
                    self.project.stand_in(body)
                run = self.project.run(f"scripts/extensions/{KEY}/hooks/sync.py", tool=tool)
                self.assertEqual(run.returncode, 0)
                self.assertIn("did not sync", run.stdout)
                self.assertIn(expected, run.stdout)

    def test_it_does_nothing_where_there_is_no_index(self) -> None:
        self.project.stand_in()
        run = self.project.run(f"scripts/extensions/{KEY}/hooks/sync.py", tool=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(self.project.called(), [])

    def test_a_sync_that_overruns_is_ended_and_said(self) -> None:
        self.index()
        self.project.stand_in("/bin/sleep 20")
        hook = self.project.module("hooks/sync.py")
        hook.SECONDS = 1
        environment = self.project.environment(True)
        kept = dict(os.environ)
        os.environ.clear()
        os.environ.update(environment)
        try:
            said = hook.outcome()
        finally:
            os.environ.clear()
            os.environ.update(kept)
        self.assertIn("did not sync", said)
        self.assertIn("longer than 1s", said)


@needs_toolkit
class TheGate(ScratchProject):
    def test_it_fails_where_the_wrapper_the_block_names_is_missing_and_names_the_fix(self) -> None:
        run = self.project.fire("check", "--fatal")
        self.assertEqual(run.returncode, 1)
        self.assertIn("scripts/codegraph", run.stderr)
        self.assertIn(f"python3 scripts/extensions/{KEY}/wrapper.py", run.stderr)

    def test_the_fix_it_names_writes_the_wrapper_and_runs_nothing(self) -> None:
        self.project.stand_in()
        fixed = self.project.run(f"scripts/extensions/{KEY}/wrapper.py", tool=True)
        self.assertEqual(fixed.returncode, 0, fixed.stderr)
        self.assertEqual(self.project.called(), [])
        self.assertTrue(os.access(self.project.root / "scripts/codegraph", os.X_OK))
        run = self.project.fire("check", "--fatal")
        self.assertEqual(run.returncode, 0, run.stderr)


REFUSE = 2
ELECT = f"python3 scripts/extensions/guards.py --elect {KEY}"


class TheGuardIsDeclared(unittest.TestCase):
    def test_it_is_a_before_search_guard_whose_file_the_package_ships(self) -> None:
        guards = declared_guards()
        self.assertEqual(sorted(guards), ["before-search"])
        self.assertTrue((PACKAGE / guards["before-search"]["run"]).is_file())

    def test_it_sees_its_own_servers_tools_and_nothing_wider(self) -> None:
        self.assertEqual(declared_guards()["before-search"]["sees"], ["mcp__codegraph__.*"])

    def test_nothing_in_the_package_writes_the_agreement_or_a_harnesss_settings(self) -> None:
        """`.slipwai/guards.json` is a person's answer and `.claude/settings.json` is the keel's to write. The
        package reads the first to say what holds, and opens neither for writing."""
        for relative in package_files():
            if relative.suffix != ".py" or relative.parts[0] == "tests":
                continue
            source = (PACKAGE / relative).read_text(encoding="utf-8")
            with self.subTest(file=relative.as_posix()):
                self.assertNotIn(".claude/settings", source)
                for line in source.splitlines():
                    if "guards.json" in line:
                        self.assertNotRegex(line, r"write_text|write_bytes|open\(|replace\(|unlink")


@needs_toolkit
@needs_guard_keel
class Guarded(ScratchProject):
    """A project with an index that defines `place_order`, a route to the CLI, and the guard agreed to."""

    def setUp(self) -> None:
        super().setUp()
        self.project.stand_in()
        self.project.index("place_order", "guard")
        self.project.agree()


class TheRule(Guarded):
    def test_a_symbol_grep_of_the_source_is_refused_before_the_index_was_asked(self) -> None:
        done = self.project.grep(path="apps/")
        self.assertEqual(done.returncode, REFUSE, done.stderr)
        for verb in ("callers", "impact", "explore"):
            self.assertIn(f"scripts/codegraph {verb} place_order", done.stderr)
        self.assertLessEqual(len(done.stderr.strip().splitlines()), 2, "a refusal is a line or two")

    def test_a_name_shaped_like_a_symbol_is_one_whether_or_not_the_index_defines_it(self) -> None:
        for pattern in ("decideCue", "OrderPlaced", "ship_order", r"\bdecideCue\b", "decideCue|ship_order"):
            with self.subTest(pattern=pattern):
                self.assertEqual(self.project.grep(pattern).returncode, REFUSE)

    def test_a_plain_word_is_a_symbol_only_where_the_index_defines_it(self) -> None:
        self.assertEqual(self.project.grep("guard").returncode, REFUSE)
        self.assertEqual(self.project.grep("order").returncode, 0)

    def test_it_is_allowed_once_the_session_asked_over_mcp(self) -> None:
        self.assertEqual(self.project.grep().returncode, REFUSE)
        self.assertEqual(self.project.asks_over_mcp().returncode, 0)
        self.assertEqual(self.project.grep().returncode, 0)
        self.assertEqual(self.project.shell("rg -n place_order apps").returncode, 0)

    def test_it_is_allowed_once_the_session_asked_through_the_shell(self) -> None:
        for command in ("scripts/codegraph callers place_order", "codegraph explore place_order",
                        "npx -y @colbymchenry/codegraph@1.6.0 impact place_order"):
            with self.subTest(command=command):
                self.project.asked().unlink(missing_ok=True)
                self.assertEqual(self.project.grep().returncode, REFUSE)
                self.assertEqual(self.project.shell(command).returncode, 0)
                self.assertEqual(self.project.grep().returncode, 0)

    def test_maintaining_the_index_is_not_asking_it(self) -> None:
        self.assertEqual(self.project.shell("scripts/codegraph sync").returncode, 0)
        self.assertEqual(self.project.grep().returncode, REFUSE)

    def test_another_session_is_still_refused(self) -> None:
        self.project.asks_over_mcp("s-1")
        self.assertEqual(self.project.grep(session="s-1").returncode, 0)
        self.assertEqual(self.project.grep(session="s-2").returncode, REFUSE)

    def test_a_delegate_that_has_not_asked_is_refused_inside_a_session_that_has(self) -> None:
        self.project.asks_over_mcp("s-1")
        self.assertEqual(self.project.grep(session="s-1", agent="a-7").returncode, REFUSE)
        self.project.asks_over_mcp("s-1", agent="a-7")
        self.assertEqual(self.project.grep(session="s-1", agent="a-7").returncode, 0)

    def test_a_search_through_the_shell_is_the_same_search(self) -> None:
        for command in ("grep -rn place_order apps", "rg place_order", "ag place_order apps/", "ack place_order",
                        "git grep -n place_order", "cd apps && rg -n 'place_order' src",
                        "rg -n place_order --glob '*.py'"):
            with self.subTest(command=command):
                self.assertEqual(self.project.shell(command).returncode, REFUSE)

    def test_a_shell_command_that_searches_nothing_is_never_refused(self) -> None:
        for command in ("ls apps", "make unit", "echo place_order", "git ls-files | grep place_order",
                        "python3 -m pytest -k place_order", "cat apps/orders.py"):
            with self.subTest(command=command):
                self.assertEqual(self.project.shell(command).returncode, 0)


class WhatIsNeverRefused(Guarded):
    def test_a_search_confined_to_documents(self) -> None:
        for searched in ({"path": "specs/001-orders"}, {"path": "docs/"}, {"glob": "*.md"}, {"type": "md"},
                         {"path": "docs/prd.md"}, {"path": "specs/001-orders/decisions.md"},
                         {"path": str(self.project.root / "specs")}):
            with self.subTest(searched=searched):
                self.assertEqual(self.project.grep(**searched).returncode, 0)
        for command in ("grep -rn place_order specs/", "rg place_order docs specs", "rg place_order -g '*.md'",
                        "grep -rn --include='*.md' place_order ."):
            with self.subTest(command=command):
                self.assertEqual(self.project.shell(command).returncode, 0)

    def test_a_glob_or_a_search_for_a_file_by_name(self) -> None:
        glob = self.project.session("before-search", self.project.harness_event("Glob", pattern="**/place_order*"))
        self.assertEqual(glob.returncode, 0)
        named = self.project.session("before-search", self.project.harness_event("Glob", pattern="place_order"))
        self.assertEqual(named.returncode, 0)
        for command in ("find . -name 'place_order*'", "fd place_order", "ls -R | grep place_order"):
            with self.subTest(command=command):
                self.assertEqual(self.project.shell(command).returncode, 0)

    def test_a_pattern_that_is_not_an_identifier(self) -> None:
        for pattern in ("done for the day", "def place_order", "place_order\\(.*\\)", "place.*order",
                        "TODO: place_order", "place_order = ", "[Pp]lace_order", ""):
            with self.subTest(pattern=pattern):
                self.assertEqual(self.project.grep(pattern, path="apps/").returncode, 0)
        self.assertEqual(self.project.shell("grep -rn 'done for the day' apps").returncode, 0)

    def test_a_search_outside_the_repository(self) -> None:
        elsewhere = self.project.root.parent / "another-checkout"
        elsewhere.mkdir()
        self.assertEqual(self.project.grep(path=str(elsewhere)).returncode, 0)
        self.assertEqual(self.project.grep(path="../another-checkout").returncode, 0)
        self.assertEqual(self.project.shell(f"cd {elsewhere} && grep -rn place_order src").returncode, 0)
        there = {**self.project.harness_event("Grep", pattern="place_order"), "cwd": str(elsewhere)}
        self.assertEqual(self.project.session("before-search", there).returncode, 0)

    def test_anything_where_there_is_no_index_and_the_reason_is_said(self) -> None:
        shutil.rmtree(self.project.root / ".codegraph")
        done = self.project.guard(json.dumps(self.project.searched(pattern="place_order")))
        self.assertEqual(done.returncode, 0)
        self.assertIn("no index", done.stderr)
        self.assertEqual(self.project.grep().returncode, 0)
        self.assertFalse((self.project.root / ".codegraph").exists(), "the guard made an index directory")

    def test_anything_where_the_index_cannot_be_read_and_the_reason_is_said(self) -> None:
        (self.project.root / ".codegraph/codegraph.db").write_bytes(b"this is not a database" * 400)
        done = self.project.guard(json.dumps(self.project.searched(pattern="place_order")))
        self.assertEqual(done.returncode, 0)
        self.assertIn("cannot be read", done.stderr)

    def test_anything_where_the_index_was_last_written_too_long_ago_and_the_date_is_said(self) -> None:
        long_ago = time.time() - 60 * 86400
        self.project.index("place_order", written=long_ago)
        done = self.project.guard(json.dumps(self.project.searched(pattern="place_order")))
        self.assertEqual(done.returncode, 0)
        self.assertIn(time.strftime("%Y-%m-%d", time.localtime(long_ago)), done.stderr)
        self.assertIn("code_index.py health", done.stderr)

    def test_anything_where_nothing_on_this_machine_could_ask_the_index(self) -> None:
        done = self.project.guard(json.dumps(self.project.searched(pattern="place_order")), tool=False)
        self.assertEqual(done.returncode, 0)
        self.assertIn("npx", done.stderr)


class TheRecordOfWhoAsked(Guarded):
    def test_it_is_kept_under_the_ignored_index_directory_by_session_and_agent(self) -> None:
        self.project.asks_over_mcp("s-1")
        self.project.asks_over_mcp("s-1", agent="a-7")
        self.assertEqual(sorted(json.loads(self.project.asked().read_text(encoding="utf-8"))),
                         ["s-1:a-7", "s-1:host"])
        self.assertIn(".codegraph/", manifest()["ignore"])
        self.assertEqual(sorted(path.name for path in (self.project.root / ".codegraph").iterdir()),
                         ["asked.json", "codegraph.db"], "a temporary file was left beside the record")

    def test_a_corrupt_record_means_nobody_has_asked_and_nothing_crashes(self) -> None:
        for body in (b"{ not json", b"\xff\xfe\x00", b"[1, 2]", b'{"s-1:host": "yesterday"}', b""):
            with self.subTest(body=body):
                self.project.asked().write_bytes(body)
                done = self.project.grep()
                self.assertEqual(done.returncode, REFUSE)
                self.assertNotIn("Traceback", done.stderr)
        self.project.asked().write_bytes(b"{ not json")
        self.project.asks_over_mcp()
        self.assertEqual(self.project.grep().returncode, 0, "a corrupt record was not replaced by a sound one")

    def test_a_record_that_cannot_be_read_means_nobody_has_asked(self) -> None:
        self.project.asked().mkdir()
        done = self.project.grep()
        self.assertEqual(done.returncode, REFUSE)
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(self.project.asks_over_mcp().returncode, 0)

    def test_it_is_bounded(self) -> None:
        kept = self.project.module("code_index.py").ASKED_KEPT
        self.project.asked().write_text(json.dumps({f"old-{number}:host": float(number)
                                                    for number in range(kept + 50)}), encoding="utf-8")
        self.project.asks_over_mcp("newest")
        held = json.loads(self.project.asked().read_text(encoding="utf-8"))
        self.assertEqual(len(held), kept)
        self.assertIn("newest:host", held)
        self.assertNotIn("old-0:host", held)

    def test_a_tool_that_is_not_the_indexes_records_nothing(self) -> None:
        told = {"v": 1, "point": "tool-use", "tool": "mcp__other__explore", "cwd": str(self.project.root),
                "session": "s-1"}
        self.assertEqual(self.project.guard(json.dumps(told), SLIPWAI_POINT="tool-use").returncode, 0)
        self.assertFalse(self.project.asked().exists())

    def test_being_told_never_refuses(self) -> None:
        told = {"v": 1, "point": "tool-use", "tool": "mcp__codegraph__codegraph_explore", "session": "s-1"}
        self.assertEqual(self.project.guard(json.dumps(told), SLIPWAI_POINT="tool-use").returncode, 0)
        self.assertEqual(self.project.guard(json.dumps(self.project.searched(pattern="place_order"))).returncode, 0)


class ItFailsOpen(Guarded):
    def refused(self, **fields: str) -> subprocess.CompletedProcess:
        return self.project.guard(json.dumps(self.project.searched(**fields)))

    def test_the_search_it_would_refuse_is_one_it_refuses_when_run_by_itself(self) -> None:
        self.assertEqual(self.refused(pattern="place_order", path="apps/").returncode, REFUSE)

    def test_a_guard_that_raises_allows_the_search_and_says_why(self) -> None:
        index = self.project.place / "code_index.py"
        index.write_text(index.read_text(encoding="utf-8")
                         + "\n\ndef guard() -> int:\n    raise RuntimeError('the floor gave way')\n", encoding="utf-8")
        alone = self.refused(pattern="place_order")
        self.assertEqual(alone.returncode, 0)
        self.assertIn("the floor gave way", alone.stderr)
        self.assertIn("allowed", alone.stderr)
        self.assertEqual(self.project.grep().returncode, 0)

    def test_a_guard_whose_module_cannot_be_loaded_allows_the_search(self) -> None:
        (self.project.place / "code_index.py").write_text("def broken(:\n", encoding="utf-8")
        done = self.refused(pattern="place_order")
        self.assertEqual(done.returncode, 0)
        self.assertIn("allowed", done.stderr)

    def test_a_keel_that_hands_no_event_is_one_under_which_nothing_is_refused(self) -> None:
        """An older keel hands a guard the query in `SLIPWAI_QUERY` and nothing on stdin: no tool, no path, no
        session. The guard cannot tell a Glob from a Grep or one session from the next, and does not guess."""
        for told in (None, "", "   ", "not json", "[]", "null"):
            with self.subTest(told=told):
                done = self.project.guard(told, SLIPWAI_QUERY="place_order", SLIPWAI_POINT="before-search")
                self.assertEqual(done.returncode, 0)
                self.assertIn("cannot judge", done.stderr)

    def test_an_event_missing_what_the_rule_needs_is_allowed_and_the_missing_field_is_named(self) -> None:
        whole = self.project.searched(pattern="place_order")
        self.assertEqual(self.project.guard(json.dumps(whole)).returncode, REFUSE)
        for missing in ("v", "tool", "session", "cwd"):
            with self.subTest(missing=missing):
                done = self.project.guard(json.dumps({word: value for word, value in whole.items()
                                                      if word != missing}))
                self.assertEqual(done.returncode, 0)
                self.assertIn(f"`{missing}`", done.stderr)
        newer = self.project.guard(json.dumps({**whole, "v": 2}))
        self.assertEqual(newer.returncode, 0)
        self.assertIn("`v`", newer.stderr)

    def test_a_field_of_the_wrong_kind_is_an_absent_one(self) -> None:
        for field, value in (("pattern", ["place_order"]), ("path", 7), ("session", {"id": 1}), ("tool", None),
                             ("command", ["grep", "place_order"])):
            with self.subTest(field=field):
                done = self.project.guard(json.dumps({**self.project.searched(pattern="place_order"),
                                                      field: value}))
                self.assertIn(done.returncode, (0, REFUSE))
                self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(self.project.guard(json.dumps({**self.project.searched(), "pattern": ["place_order"]}))
                         .returncode, 0)

    def test_it_runs_no_command_and_opens_no_connection(self) -> None:
        """The stand-in `codegraph` on PATH records every call, and a `sitecustomize` makes starting a process or
        opening a socket raise. Fail-open would turn either into an allowed search, so the proof is a refusal."""
        poison = self.project.root.parent / "poison"
        poison.mkdir()
        (poison / "sitecustomize.py").write_text(
            "import socket, subprocess\n"
            "def never(*a, **k):\n    raise RuntimeError('the guard reached outside itself')\n"
            "subprocess.Popen.__init__ = never\nsocket.socket.__init__ = never\nsocket.create_connection = never\n",
            encoding="utf-8")
        done = self.project.guard(json.dumps(self.project.searched(pattern="place_order")), PYTHONPATH=str(poison))
        self.assertEqual(done.returncode, REFUSE, done.stderr)
        told = {"v": 1, "point": "tool-use", "tool": "mcp__codegraph__codegraph_explore", "session": "s-1",
                "cwd": str(self.project.root)}
        self.assertEqual(self.project.guard(json.dumps(told), PYTHONPATH=str(poison)).stderr, "")
        self.assertEqual(self.project.called(), [], "the guard ran the CLI")

    def test_it_answers_well_inside_its_budget(self) -> None:
        began = time.monotonic()
        self.assertEqual(self.refused(pattern="place_order").returncode, REFUSE)
        self.assertLess(time.monotonic() - began, 2.5)
        self.assertEqual(declared_guards()["before-search"]["budget"], "5s")

    def test_it_leaves_no_bytecode_in_the_project(self) -> None:
        self.refused(pattern="place_order")
        self.project.grep()
        self.assertEqual([path for path in self.project.place.rglob("__pycache__")], [])


@needs_toolkit
@needs_guard_keel
class NobodyAgreed(ScratchProject):
    def test_a_guard_nobody_agreed_to_refuses_nothing_and_records_nothing(self) -> None:
        self.project.stand_in()
        self.project.index("place_order")
        self.assertEqual(self.project.grep().returncode, 0)
        self.project.asks_over_mcp()
        self.assertFalse(self.project.asked().exists())


@needs_toolkit
@needs_guard_keel
class WhatTheBlockSaysHoldsTheRule(ScratchProject):
    def adopted(self) -> None:
        self.project.stand_in()
        self.assertEqual(self.project.init().returncode, 0)
        self.project.calls.unlink()

    def test_where_a_guard_is_available_and_nobody_agreed_it_names_the_command_that_agrees(self) -> None:
        self.adopted()
        block = self.project.agents()
        self.assertIn("nobody has agreed to it", block)
        self.assertIn(ELECT, block)
        self.assertIn("Claude Code", block)
        self.assertIn("asking the index first is the session's own to do", block)
        self.assertNotIn("a guard this project agreed to", block)

    def test_where_it_is_agreed_to_and_held_it_says_what_refuses_and_what_never_is(self) -> None:
        self.adopted()
        self.project.agree()
        run = self.project.fire("project", tool=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        block = self.project.agents()
        self.assertIn("a guard this project agreed to", block)
        self.assertIn("In Claude Code", block)
        self.assertIn(f"scripts/extensions/{KEY}/{declared_guards()['before-search']['run']}", block)
        self.assertNotIn("nobody has agreed to it", block)
        check = self.project.run("scripts/extensions/project.py", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_where_the_harness_holds_no_guard_it_promises_none(self) -> None:
        self.project.harness = "gemini"
        self.adopted()
        self.project.agree()  # agreed to, and still not held: Gemini CLI has no hook before a search
        self.project.fire("project", tool=True)
        block = self.project.agents()
        self.assertIn("In Gemini CLI, nothing can refuse a search", block)
        self.assertIn("asking the index first is the session's own to do", block)
        self.assertNotIn("a guard this project agreed to", block)
        self.assertNotIn(ELECT, block, "agreeing would change nothing on a harness that holds no guard")

    def test_two_harnesses_are_each_told_their_own(self) -> None:
        self.adopted()
        (self.project.root / ".specify").mkdir()
        (self.project.root / ".specify/integration.json").write_text(
            json.dumps({"installed_integrations": ["claude", "gemini"]}), encoding="utf-8")
        self.project.agree()
        self.project.fire("project", tool=True)
        block = self.project.agents()
        self.assertIn("In Claude Code, a guard this project agreed to", block)
        self.assertIn("In Gemini CLI, nothing can refuse a search", block)

    def test_taking_the_agreement_back_is_said_at_the_next_projection(self) -> None:
        self.adopted()
        self.project.agree()
        self.project.fire("project", tool=True)
        self.assertEqual(self.project.run("scripts/extensions/guards.py", "--remove", KEY).returncode, 0)
        self.project.fire("project", tool=True)
        self.assertIn("nobody has agreed to it", self.project.agents())

    def test_the_block_is_what_the_hook_was_told_and_what_the_drift_check_reads(self) -> None:
        """A hook is handed `SLIPWAI_GUARDS_HELD`; the drift check imports `GUIDANCE` with no such variable. The
        two must read the same block, or every `make check-extensions` after a `make agents` is red."""
        self.adopted()
        self.project.fire("project", tool=True)
        check = self.project.run("scripts/extensions/project.py", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn(self.project.canonical(), self.project.agents())


@needs_toolkit
class UnderAKeelThatTellsAnExtensionNothing(ScratchProject):
    def test_the_block_promises_no_guard(self) -> None:
        """An older keel has no `guard_harness.py` and sets no `SLIPWAI_GUARDS_HELD`. Told nothing, the block says
        nothing holds the rule, which is what is true there: the guard is handed no search to judge."""
        for script in ("guard_harness.py", "guard_offer.py"):
            (self.project.root / "scripts/extensions" / script).unlink(missing_ok=True)
        self.project.stand_in()
        self.assertEqual(self.project.init().returncode, 0)
        block = self.project.agents()
        self.assertIn("No guard holds this here", block)
        self.assertIn("asking the index first is the session's own to do", block)
        self.assertNotIn("a guard this project agreed to", block)
        check = self.project.run("scripts/extensions/project.py", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)


@needs_toolkit
@needs_guard_keel
class AnUpgradeFromTheVersionBefore(ScratchProject):
    BEFORE = "v1.0.1"

    def files_before(self) -> dict[str, bytes]:
        """The package as it was released, from this checkout's own tag; skipped where the tag is not here."""
        try:
            names = subprocess.run(["git", "-C", str(PACKAGE), "ls-tree", "-r", "--name-only", self.BEFORE],
                                   capture_output=True, text=True, timeout=60)
        except OSError:
            self.skipTest("no git here to read the released package with")
        if names.returncode != 0:
            self.skipTest(f"this checkout has no {self.BEFORE} tag to upgrade from")
        return {name: subprocess.run(["git", "-C", str(PACKAGE), "show", f"{self.BEFORE}:{name}"],
                                     capture_output=True, timeout=60, check=True).stdout
                for name in names.stdout.split() if name != "extension.json"}

    def test_it_ends_green_with_the_guard_offered_and_not_agreed_and_nobody_running_a_command(self) -> None:
        project, now = self.project, {path: (self.project.place / path).read_bytes() for path in package_files()}
        # The project as 1.0.1 left it: that version's files, its `./init` run, and no guard on offer.
        shutil.rmtree(project.place)
        for name, body in self.files_before().items():
            target = project.place / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        offered = project.root / "scripts/extensions/available-guards.json"
        offered.write_text("{}", encoding="utf-8")
        project.stand_in()
        self.assertEqual(project.init().returncode, 0)
        project.index("place_order")
        self.assertIn("No hook refuses a text search", project.agents())
        self.assertEqual(project.run("scripts/extensions/project.py", "--check").returncode, 0)
        project.calls.unlink()
        # What `slipwai migrate` does: this version's files, what it offers, and then the projection.
        shutil.rmtree(project.place)
        for path, body in now.items():
            target = project.place / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        offered.write_text(json.dumps({KEY: declared_guards()}), encoding="utf-8")
        self.assertEqual(project.run("scripts/extensions/hooks.py", "--elect", KEY).returncode, 0)
        projected = project.run("scripts/extensions/project.py", tool=True)
        self.assertEqual(projected.returncode, 0, projected.stderr)
        # Offered, in the keel's own line, and agreed to by nobody.
        self.assertIn(ELECT, projected.stdout + projected.stderr)
        registry = project.root / ".slipwai/guards.json"
        agreed = json.loads(registry.read_text(encoding="utf-8")).get("guards", {}) if registry.is_file() else {}
        self.assertEqual(agreed, {})
        self.assertFalse((project.root / ".claude").exists())
        # Green: the block is this version's, the drift check and the gate pass, and nothing is refused.
        self.assertNotIn("No hook refuses a text search", project.agents())
        self.assertIn("nobody has agreed to it", project.agents())
        check = project.run("scripts/extensions/project.py", "--check")
        self.assertEqual(check.returncode, 0, check.stderr)
        gate = project.fire("check", "--fatal", tool=True)
        self.assertEqual(gate.returncode, 0, gate.stderr)
        self.assertEqual(project.grep(path="apps/").returncode, 0)
        self.assertEqual([call for call in project.called() if "install" in call], [], "an upgrade installed")


if __name__ == "__main__":
    unittest.main()
