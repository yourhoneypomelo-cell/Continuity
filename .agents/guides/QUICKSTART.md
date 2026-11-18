# Quickstart

Install the template, run the first session and switch between tools.

## Requirements

- **Python 3.9** or newer on the PATH as `python3` or `python` (macOS often has only `python3`). No packages
  are needed. From the project root you can run `.agents/tools/ws` (Unix/macOS) or `.\.agents\tools\ws.cmd` (Windows)
  instead of naming the interpreter.
- An agent tool that can read files and run shell commands.
- Version control is recommended. The workspace works without it.

## Install

New project: unzip `dist/agent-workspace-<version>.zip` from the template folder into an empty
folder. The zip has no top-level folder, so the empty folder becomes the project root.
The package already contains the hidden folders `.agents`, `.gemini` and `.kiro`.

Existing project: preview first, then install from the template folder.

```text
.agents/tools/ws install --target "D:/code/my-app" --dry-run
.agents/tools/ws install --target "D:/code/my-app"
```

Or `python3 .agents/tools/ws.py …` / `python .agents/tools/ws.py …` if you prefer naming the interpreter.

The installer never overwrites a file. An existing README.md is kept.
If the project already has an AGENTS.md, CLAUDE.md or `.gemini/settings.json`, add `--merge`.
The old AGENTS.md text is kept under a "Project rules" heading.

The installer also writes small `.gitignore` and `.gitattributes` files inside `.agents/` and
`docs/`. They keep the hash cache and raw transcripts out of version control and keep line endings
stable across Windows and Unix checkouts.

## First session

Open the project in an agent tool and send:

> Read AGENTS.md and start. The goal is: [one sentence].

The agent runs `ws init`, inspects the code, fills ARCHITECTURE.md, records the first requirements
and tasks, and checkpoints. Check the result with `python .agents/tools/ws.py brief`.

## Daily use

You talk to the agent as usual. The agent records requirements, decisions, questions and
preferences as they come up and verifies tasks before calling them done.
Useful requests:

| You say | The agent does |
| --- | --- |
| "Save now." | `ws checkpoint --keep --stop "..." --next "..."` |
| "I'm switching tools." | `ws checkpoint` and confirms READY |
| "What's open?" | `ws brief` |
| "Clean up the docs." | `ws compact` |

## Recording a change of direction

`ws add decision` and `ws set D2` accept `--message MID --supersedes D1 --next STEP` together.
Add `--observed` for verified progress and `--artifact` for its location, including another repository and commit.
The brief flags an older handoff step until `ws card --set next_step=...` confirms it or a checkpoint revises it.
Saving a checkpoint still releases the work. When the brief flags a decision change, the same pending review
appears in `ws check --ready`. Read the decision, update the next step and checkpoint. To keep a step that
still applies, confirm it explicitly with `ws card --set "next_step=..."` before checkpointing.
The brief uses recorded change order, including edits to older decisions and archived log entries.
Use `--risk-until` on a card or checkpoint for an observation with a known expiry and UTC offset.

## Matching the delivered file

When an outside service issues a receipt, record its reference, the scope of the result and the
SHA-256 of the approved file. Get the digest from the accepted submission or its trusted record.
`--candidate` names the file the normal build or handoff would actually deliver.

```text
ws receipt record T1 --ref receipt-17 --scope "component A" --result "accepted" --file accepted.zip --sha256 <approved-digest> --candidate build/output.zip
ws receipt check T1
```

An outer ZIP can be checked with `--container submission.zip --member payload/accepted.zip`.
Supply `--container-sha256` when the external receipt also gives the outer digest.
`ws verify` checks the binding before and after acceptance. `ws check --ready` checks it again.
`ws receipt list T1` keeps prior submissions. The latest receipt in each task and scope is current.

Before sharing, `ws receipt audit PATH` scans a file or folder and opens nested ZIP members in memory.
It reports paths and known credential kinds. Receipts check approved deliveries.
Template export checks the files it copies.
Use `--resolve-risk` when this receipt settles the risk on the card. The receipt keeps the observed risk and its date.

## Resuming an interrupted batch

```text
ws batch set import-A --task T1 --status stopped --stop "First 12 files passed" --next "Check files 13 to 15" --entry docs/guides/import.md --evidence reports/first-12.txt --artifact build/import.zip
```

The new window sees the stop point, evidence and restart entry in `ws brief`. The artifact may also
name a separate snapshot and revision. Open the reference to confirm its contents.
Update the same batch with `--status done` after its remaining checks pass. `ws batch list` shows all entries.
Omit `--evidence` and `--artifact` to retain their last values. Supply a new path to replace one, or use
`--artifact=` or `--evidence=` to clear it. `ws batch list --task T1 --history` shows earlier stages and references.

## Switching windows or tools

```text
window A: "I'm switching."  ->  ws checkpoint  ->  READY
window B: "Read AGENTS.md and continue."  ->  ws brief  ->  ws start  ->  next step
```

If window A died before saving, window B still works. `ws start` takes over and lists the files
window A changed after its last checkpoint, so nothing is lost silently.

If a tool does not load AGENTS.md by itself, send this first:

> Read AGENTS.md in the project root and follow "Start of every session".

## Automatic transcripts

Hooks copy each session's transcript into `docs/chats/` and inject `ws brief` at session start.
Copying chats from AI tools that have no hook waits for your answer: at `init` the agent asks once,
and messages from before that moment stay out. In a git project it also asks whether git ignores
`docs/chats/`. Details: HOSTS.md, "Importing from host stores".

```text
python .agents/tools/ws.py hooks enable claude
python .agents/tools/ws.py hooks enable cursor
python .agents/tools/ws.py hooks enable gemini
python .agents/tools/ws.py hooks enable copilot
```

Run the line for each tool you use, then start a new session in that tool. HOSTS.md lists what
each host supports and how to confirm the hook ran.

## Upgrading within version 3

Run the tool of the new template folder against the project, first to see the plan:

```text
python .agents/tools/ws.py upgrade --target "D:/code/my-app" --dry-run
python .agents/tools/ws.py upgrade --target "D:/code/my-app"
```

Run it while no session works in the project. A template file the project never edited is replaced. An
edited guide, skill or adapter is kept, and the new version goes to `docs/archive/upgrades/<folder>/new/`
for a hand merge; the command then exits with 1. The rules under "## Project rules" in AGENTS.md are kept
under the new contract. Tool code the project changed stops the upgrade before anything is written, so the
tool never mixes two versions. `docs/` and `.agents/hooks.json` are not touched, and hook settings get this
version's entries while the user's own stay. The checkpoint takes in the new files, so a READY workspace
stays READY.

Every replaced file is backed up in the upgrade folder. `--rollback <folder>` puts them back, and
`ws doctor` checks hooks and tool files afterwards. A project without `.agents/template/MANIFEST.json`
needs `--assume-base <the release zip or folder it came from>`; otherwise every file that differs from the
new version counts as edited. `--scan <folder>` lists the workspaces under a folder with their versions.

Before 3.7.0 there was no upgrade command: the four folders `.agents/tools`, `.agents/guides`,
`.agents/skills` and `.agents/template` were copied over, followed by `ws start` and `ws checkpoint`.

## Upgrading from version 2

```text
python .agents/tools/ws.py migrate --target "D:/code/my-app" --dry-run
python .agents/tools/ws.py migrate --target "D:/code/my-app"
```

Run it from a version 3 template folder. If a v2 session still holds the workspace, close that
agent window and add `--force`; nothing it changed is discarded. The migration backs up
every replaced file to `docs/archive/v2-backup/`, converts the tables and card, moves closed rows
to CLOSED_ITEMS.md and marks completed tasks `unverified` so they are tested again.
Afterwards open the project and say "Read AGENTS.md and continue."

## Compatibility between versions

A stored format changes only together with its version mark. A tool reads every older mark it knows and
refuses a newer one with a message to upgrade, so an older tool never misreads newer data.

| Part | Mark | In 3.9.0 | Older forms |
| --- | --- | --- | --- |
| State line in HANDOFF.md | `schema` | continuity.v3, unchanged | continuity.v2 is converted once by `ws migrate` |
| Evidence in `docs/archive/checks/` | `rules` | Summary rules 2 since 3.7.0; evidence without the field is rules 1 | Read again with the rules it records, so it stays valid |
| Checkpoint manifests | optional keys | `rebaselined` and `upgraded` after an upgrade (3.7.0); `after_upgrade` in the first session after one (3.8.0); `messages_open`, the messages open at the seal (3.9.0) | Older tools ignore them. Without `messages_open` every open message blocks READY |
| Template manifest | optional keys | `maintainer_files`, `source_modified` (3.7.0) | 3.6.x ignores them |
| WORKSPACE block | optional keys | `stale_evidence`, block by default (3.8.0); `credential_files`, `chat_import` and `chat_import_since` (3.9.0) | Older tools ignore them; 3.8 reads `"plain"` as every file and imports at every start |
| Task Scope | words | `new:<path>`, `resource:<name>`, `tree:` (3.8.0) | A 3.7.x tool reads them as plain words |
| Workspace lock | file | A system lock on `.agents/cache/ws.flock` (ws 3.9.0) | The `ws.lock` of ws 3.8 and older still counts while its process runs, and `WS_LOCK=legacy` uses it instead; **ws 3.10.0** drops both (not Python 3.10) |
| Transcript headings in `docs/chats/` | words | The message ID after the time, as in `[m3fa91c02e7b]` (3.9.0) | A heading without one is read as before; a 3.8 tool does not read headings that carry one |
| Message IDs in RECONCILE_LOG | length | 12 hex digits, covering the transcript and the message number (3.9.0) | The 10-digit IDs of 3.8, the hash of the text alone, stay valid for the messages saved then |

Announced for **ws 3.10.0**: the `ws.lock` of ws 3.8 and `WS_LOCK=legacy` stop counting, so every window must run
**ws 3.9** or later by then. A version that stops reading an older mark says so here first, one release ahead.

Rules 2 reads two kinds of output differently from rules 1: a unittest run whose program prints an "OK"
or "FAILED" line of its own, and a log line such as "FAILED to connect". To go back to 3.6.x, run
`ws upgrade --rollback` from the newer template: it lists the evidence 3.6.x would refuse, and
`ws verify` runs those tasks again.
