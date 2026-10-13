# Changelog

Release notes, newest first, one entry per released version; the entry being written is `changelog.d/`.

## 1.0.0

**CodeGraph ships as an extension package: `slipwai extension install codegraph`, elected in a project with
`./init --extension codegraph`.** The index, the pointer in `AGENTS.md` that sends an agent to the graph
before it reaches for grep, the MCP server named in every installed harness's committed project file, and
the gate that notices an index nothing is maintaining.

**It carries its own `code_index.py`.** The keel stopped shipping one product's 573-line database keeper to
every project in slice 6.1c, and the module moved here — where the entry point that imports it and the gate
that loads it both are. A missing CodeGraph CLI is still a message and never a failed `./init`.
