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
import stat
import subprocess
import sys
import tempfile
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


def manifest() -> dict:
    return json.loads((PACKAGE / "extension.json").read_text(encoding="utf-8"))


def declared() -> dict[str, dict]:
    """The manifest's hooks in the long form the keel resolves them to."""
    return {name: ({"run": body} if isinstance(body, str) else dict(body))
            for name, body in manifest().get("hooks", {}).items()}


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
                "SLIPWAI_INTEGRATION": "claude"}

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
            for name in ("guidance", "code_index", "init", "wrapper"):
                sys.modules.pop(name, None)
        return loaded

    def canonical(self) -> str:
        return self.module("init.py").GUIDANCE.strip("\n")


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


if __name__ == "__main__":
    unittest.main()
