# Changelog

Release notes, newest first, one entry per released version; the entry being written is `changelog.d/`.

## 1.1.0 — MINOR

**The guard is back: a search of the source for a symbol waits until the session has asked the index.** 1.0.0 promised a hook that refused such a search and the keel's version 2 wrote none; 1.0.1 took the promise out. The package now declares a guard at the keel's `before-search` point (`guards/ask_the_index.py`). A Grep, or `grep`, `rg`, `ag`, `ack` or `git grep` through the shell, whose pattern is only names the index defines or names shaped like one, is refused with `scripts/codegraph callers|impact|explore <symbol>` to ask instead, until that session, or that delegate inside it, has asked the index once: over MCP, which the guard declares it `sees`, or by a query verb through the shell. Who has asked is kept in `.codegraph/asked.json`, which Git ignores.

**Nothing turns it on but a person.** Electing the extension does not agree to its guard, and neither does an upgrade: `slipwai migrate` and `make agents` say that it is on offer, and `python3 scripts/extensions/guards.py --elect codegraph` agrees. A project that had 1.0.1 and takes this version stays green with nobody running a command, with nothing refused. After agreeing, run `make agents`: the `AGENTS.md` block says what holds the rule, so it changes with the answer, and `make check-extensions` reports the old paragraph as drift until it is rewritten.

**It refuses only what the index can answer, and allows wherever it cannot tell.** Never refused: a search confined to documents (`specs/`, `docs/`, `*.md`, by path or by filter), a Glob or a file-name search, words or a regular expression, a search outside the repository. Allowed with the reason said on stderr: no index, an index that cannot be read, one last written more than 14 days ago, no route to the CLI on this machine, and an event that does not name the tool, the session or the directory. It runs no command and opens no connection, and anything that goes wrong inside it allows the search. A `sed -n '/name/p'` is no longer counted as a search, and a file filter such as `--include='*.md'` now confines a search to documents wherever it starts.

**The block says what holds the rule, per harness.** Where the keel can refuse before a search (Claude Code) and the guard is agreed to, it says a guard refuses; where it could and nobody agreed, it says nothing refuses and names the command that agrees; where the harness has no such moment (Cursor, Gemini CLI, and any other), it says asking the index first is the session's own to do.

**It needs a keel with slipwai #121**: the search event on a guard's stdin, `sees`, and `SLIPWAI_GUARDS_HELD`. The manifest has no field to state that, since the keel schema `core` names did not move, so on an older keel this version installs and behaves as 1.0.1 did: the guard is handed only the query, cannot judge, and allows every search, and the block says no guard holds.

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
