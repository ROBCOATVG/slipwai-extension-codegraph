# Changelog

Release notes, newest first, one entry per released version; the entry being written is `changelog.d/`.

## 1.0.1 — PATCH

**`scripts/codegraph` is there to be run.** The `AGENTS.md` block told every agent to ask the index with `scripts/codegraph callers`, `impact` and `explore`, and a project on slipwai 2.1 had no such file: version 1 of the keel shipped it, the crossing removed it, and this package wrote nothing in its place, so a delegate that followed the page ran a file that was not there. The package ships the wrapper's source (`bin/codegraph`) and `./init --extension codegraph` writes it, executable, before anything that needs the CLI — it reaches the index through `npx`. It is a tracked file: commit it. A project that elected 1.0.0 gets it from `python3 scripts/extensions/codegraph/wrapper.py`, which installs and indexes nothing, and the gate fails and names that command until it has.

**The block names what a 2.1 project has.** The gate is `make check-extensions`, which runs this extension's `hooks/check.py`; `make check-codegraph` is gone. The repair by hand is `python3 scripts/extensions/codegraph/code_index.py health`, not a path under `scripts/agents/`. The stage boundary is `commands/sail.md`'s. And three sentences described rows version 1 of the keel wrote into Claude Code's settings — a hook that refused a symbol search, a rebuild when a session opened, a runner that repaired the database before every iteration — which nothing writes now, so the block no longer promises them: no hook refuses a text search.

**`hooks/sync.py` ships.** `extension.json` has declared it at `after-stage` since 1.0.0 and the package did not carry it, so the toolkit reported *not in this project* after every rung and nothing synced. It syncs the index inside the point's 30s budget, exits 0 whatever happened, and says what it could not do. The declaration no longer names `implement` and `converge`: a captain fires `after-stage` for the rungs it runs, `drive` and `decide`, so a hook asking for those two stages was never called.

**`make agents` rewrites a drifted block and writes the wrapper, and installs nothing.** The package declared no `project` hook, so that point fell to `init.py`, which installs CodeGraph and indexes the repository — or, where the CLI is missing, stops before the block. `hooks/project.py` rewrites the block from `GUIDANCE` and writes `scripts/codegraph` where it is missing or an older copy. So a project that elected 1.0.0 and takes this version through `slipwai migrate` or `make agents` has the wrapper without anybody running a command, and the gate that now asks for it passes. The wrapper is a tracked file: commit it.

## 1.0.0

**CodeGraph ships as an extension package: `slipwai extension install codegraph`, elected in a project with
`./init --extension codegraph`.** The index, the pointer in `AGENTS.md` that sends an agent to the graph
before it reaches for grep, the MCP server named in every installed harness's committed project file, and
the gate that notices an index nothing is maintaining.

**It carries its own `code_index.py`.** The keel stopped shipping one product's 573-line database keeper to
every project in slice 6.1c, and the module moved here — where the entry point that imports it and the gate
that loads it both are. A missing CodeGraph CLI is still a message and never a failed `./init`.
