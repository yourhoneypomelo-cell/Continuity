"""Public command line arguments."""
import argparse
from pathlib import Path

from .capture import IMPORT_HOSTS
from .hooks import HOSTS
from .schema import VERSION


COMMANDS = '''commands:
  brief [--retired]          print the resume summary, or every retired row in full (read-only)
  turn                       print the per-turn reminder used by prompt-submit hooks (read-only)
  note TEXT                  append one progress line to SESSION_LOG; cheap, use it every few turns
  idea TEXT                  an unconfirmed idea as a bullet in the Idea pool of REQUIREMENTS.md, without an ID
  status                     ownership, revision and unsaved files as JSON (read-only)
  check [--ready] [--strict] validate the workspace (read-only)
  init --goal TEXT           first run only: record the goal and claim the workspace
  start [--session KEY]      claim the workspace; with the key the brief hook printed, resume it after compaction
  start --task T5 [--task T6]   claim only these tasks, so another session can work on others in parallel
  add TABLE --set f=v ...    add a row; the ID is assigned and the matching log row written
  set ID --set f=v ...       change a row; status changes and edits are logged
  card --set f=v ...         change handoff card fields
  goal TEXT [--source S]     change the goal when the user widens or narrows it; the old text is logged
  verify [IDs] [--done] -- CMD   run acceptance, store evidence, optionally mark tasks done
  receipt record|check|list  bind an external result to the approved SHA-256 and check the delivery file
  batch set|list             record a batch stop point, remaining work, proof and restart entry
  chats audit                scan saved chats and revisions; show paths and credential kinds only
  verify --stale             run again every done task whose files changed after it was verified
  checkpoint --stop TEXT --next TEXT [--keep]   save and seal; releases the workspace unless --keep
  compact [--dry-run] [--prune-evidence]        move closed rows to CLOSED_ITEMS.md, roll logs
  snapshot --label NAME [PATHS]                 zip the documents before a large reorganization; no restore
  hooks enable|show|disable HOST  write or remove hook settings: claude, codex, cursor, gemini, copilot, kiro, antigravity,
                             grok, codebuddy, workbuddy, qoder, qwen; --python CMD sets the interpreter command,
                             --absolute writes absolute paths for hosts that start hooks in another folder
  capture --host H --event E read a hook payload on stdin and copy the transcript
  chats import HOST [--all]  copy this project's sessions from a local store: kimi, codex, antigravity,
                             kiro, cursor, workbuddy, codebuddy, qoder, qwen, gemini, dsh; --all also
                             copies messages from before the workspace was set up
  reconcile [ID --ids R1,T2 | --reason "chat: ..."]   list user messages not yet matched to rows, or mark one
  reconcile all --reason "..." --confirm N   give the N open messages one reason, after reading them
  reconcile --review [--last N]  the last user messages beside the rows or reasons that account for them
  lint                       advisory layout and wording checks for reusable documents
  doctor [--json]            hooks, interpreter, session identity and tool files at a glance, each problem with its
                             fix (read-only); exit 1 when a problem is found
  tidy [--dry-run] [--force] remove template maintainer files an older install left here; add search ignore files
  upgrade --target DIR       bring a project to this template version (from the new template folder); --dry-run
                             first, --rollback NAME to undo, --scan FOLDER to list the workspaces under a folder
  install --target DIR       copy this template into a project (from the template folder); --merge --dry-run --diff
                             shows what merging would change
  export --output DIR        write a clean template copy and a zip
  migrate                    convert a continuity.v2 workspace in place
  release [--keep-old] [--skip-full REASON]   maintainer: gate, stamp, build and test dist/agent-workspace-<version>.zip
  stamp                      maintainer: update .agents/template/MANIFEST.json only

tables: requirements, questions, preferences, features, tasks, decisions
'''


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='ws.py', description=f'Continuity workspace tool {VERSION}',
                                epilog=COMMANDS, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, default=None, help='project root (default: the folder that holds .agents)')
    subs = p.add_subparsers(dest='command', required=True, metavar='COMMAND')

    def owned(sub):
        sub.add_argument('--writer', help='session label; required with shared ownership')
        sub.add_argument('--rev', type=int, help='expected revision; required with shared ownership')
        sub.add_argument('--session', help='session key printed by the brief hook, on a host without a session variable')
        return sub

    brief = subs.add_parser('brief')
    brief.add_argument('--hook', choices=HOSTS, help='print in the session-start hook format of this host')
    brief.add_argument('--retired', action='store_true', help='list every retired row in full, newest first')
    turn = subs.add_parser('turn')
    turn.add_argument('--hook', choices=HOSTS, help='print in the prompt-submit hook format of this host')
    note = subs.add_parser('note')
    note.add_argument('text', nargs='+')
    note.add_argument('--session', help='session key printed by the brief hook, on a host without a session variable')
    idea = owned(subs.add_parser('idea'))
    idea.add_argument('text', nargs='+')
    subs.add_parser('status')
    check = subs.add_parser('check')
    check.add_argument('--ready', action='store_true', help='also require a released, sealed workspace')
    check.add_argument('--strict', action='store_true', help='also check links in reusable documents')
    check.add_argument('--adapters', action='store_true', help='also check adapters marked pending')
    init = subs.add_parser('init')
    init.add_argument('--goal', required=True)
    init.add_argument('--writer')
    init.add_argument('--session', help='session key printed by the brief hook')
    init.add_argument('--chat-import', choices=('on', 'off'), help="the user's answer: may ws start copy this "
                      "project's chats from host stores into docs/chats/")
    init.add_argument('--chat-capture', choices=('on', 'off'), help='whether enabled hooks may copy live chat')
    init.add_argument('--chats-git', choices=('keep', 'ignore'), help="the user's answer for a git project: "
                      'ignore adds docs/chats/ to .gitignore')
    start = subs.add_parser('start')
    start.add_argument('--writer')
    start.add_argument('--session', help='session key printed by the brief hook; resumes ownership after compaction')
    start.add_argument('--force', action='store_true', help='take over although the owner window still runs or ownership is shared; give --reason')
    start.add_argument('--task', action='append', default=[], metavar='ID',
                       help='claim only these tasks, so another session can work on others at the same time')
    start.add_argument('--reason')
    add = owned(subs.add_parser('add'))
    add.add_argument('table')
    add.add_argument('--set', action='append', default=[], metavar='FIELD=VALUE')
    add.add_argument('--source', help='where this came from, for example "user 2026-10-31"')
    set_ = owned(subs.add_parser('set'))
    set_.add_argument('id')
    set_.add_argument('--set', action='append', default=[], metavar='FIELD=VALUE', required=True)
    set_.add_argument('--source')
    set_.add_argument('--move-detail', metavar='PATH',
                      help='append the full current row to PATH under docs/specs/ or docs/reports/, then apply --set')
    for edit in (add, set_):
        edit.add_argument('--message', help='captured user message ID to reconcile with the row')
        edit.add_argument('--supersedes', action='append', metavar='D1,D2', help='decisions replaced by this decision')
        edit.add_argument('--next', help='set the handoff next step for this adopted decision')
    card = owned(subs.add_parser('card'))
    card.add_argument('--risk-until', help='expiry time with UTC offset for the risk observation')
    card.add_argument('--set', action='append', default=[], metavar='FIELD=VALUE', required=True)
    goal = owned(subs.add_parser('goal'))
    goal.add_argument('text', nargs='+', help='the new goal, one sentence')
    goal.add_argument('--source', help='for example "user 2026-11-05"')
    verify = owned(subs.add_parser('verify'))
    verify.add_argument('ids', nargs='*', metavar='TASK')
    verify.add_argument('--done', action='store_true', help='mark the tasks done when the evidence is accepted')
    verify.add_argument('--kind', choices=('test', 'check'))
    verify.add_argument('--report', choices=('json', 'junit'), help='the command writes a report to $CONTINUITY_REPORT')
    verify.add_argument('--label')
    verify.add_argument('--timeout', type=int, default=900)
    verify.add_argument('--because', help='why the command differs from the task acceptance; logged')
    verify.add_argument('--stale', action='store_true', help='run again every done task whose files changed after it '
                        'was verified, once per acceptance command')
    cp = owned(subs.add_parser('checkpoint'))
    cp.add_argument('--stop', required=True, help='exact stop point, one line')
    cp.add_argument('--next', required=True, help='concrete next step, one line')
    cp.add_argument('--set', action='append', default=[], metavar='FIELD=VALUE', help='other card fields')
    cp.add_argument('--risk-until', help='expiry time with UTC offset for the risk observation')
    cp.add_argument('--keep', action='store_true', help='keep ownership (intermediate save)')
    compact = owned(subs.add_parser('compact'))
    compact.add_argument('--dry-run', action='store_true')
    compact.add_argument('--prune-evidence', action='store_true', help='delete evidence files no row references')
    snap = subs.add_parser('snapshot', help='zip the documents (and named paths) before a large reorganization')
    snap.add_argument('paths', nargs='*', help='extra product paths to include')
    snap.add_argument('--session', help='session key printed by the brief hook, on a host without a session variable')
    snap.add_argument('--label', required=True, help='for example before-docs-merge')
    snap.add_argument('--pin', action='store_true', help='never prune this snapshot')
    hooks = subs.add_parser('hooks')
    hooks.add_argument('action', choices=('enable', 'show', 'disable'))
    hooks.add_argument('host', choices=HOSTS)
    hooks.add_argument('--python', metavar='CMD', help='interpreter command the hooks run, such as python3 or "py -3"; '
                       'by default the first of python, python3 and py -3 that is 3.9 or newer')
    hooks.add_argument('--absolute', action='store_true', help='write the interpreter and ws.py as absolute paths, for '
                       'a host that starts hooks from another folder; the files then point at this copy of the project')
    cap = subs.add_parser('capture')
    cap.add_argument('--host', required=True)
    cap.add_argument('--event', default='unknown')
    chats = subs.add_parser('chats')
    chats.add_argument('action', choices=('import', 'audit'))
    chats.add_argument('host', nargs='?', choices=IMPORT_HOSTS)
    chats.add_argument('--all', action='store_true', help='also copy messages from before the workspace was set up')
    rec = subs.add_parser('reconcile')
    rec.add_argument('message', nargs='?', help='message ID from the list, or "all" with --reason and --confirm')
    rec.add_argument('--session', help='session key printed by the brief hook, on a host without a session variable')
    rec.add_argument('--ids', help='rows that record the message, for example R4,P2')
    rec.add_argument('--reason', help='why no row is needed: question, chat, duplicate, superseded, out-of-scope, secret')
    rec.add_argument('--confirm', type=int, metavar='N', help='with "all": how many open messages it marks')
    rec.add_argument('--limit', type=int, default=20)
    rec.add_argument('--review', action='store_true', help='show the last user messages beside the rows or reasons '
                     'that account for them')
    rec.add_argument('--last', type=int, default=20, help='how many messages --review shows')
    receipt = subs.add_parser('receipt')
    actions = receipt.add_subparsers(dest='action', required=True)
    record = owned(actions.add_parser('record'))
    record.add_argument('task')
    for arg in ('file', 'sha256', 'ref', 'scope', 'result'):
        record.add_argument('--' + arg, required=True)
    for arg in ('candidate', 'container', 'member', 'container-sha256'):
        record.add_argument('--' + arg)
    check_receipt = actions.add_parser('check')
    check_receipt.add_argument('task')
    check_receipt.add_argument('--file', help='also compare a particular candidate')
    check_receipt.add_argument('--ref')
    actions.add_parser('list').add_argument('task', nargs='?')
    batch = subs.add_parser('batch')
    actions = batch.add_subparsers(dest='action', required=True)
    update = owned(actions.add_parser('set'))
    update.add_argument('name')
    update.add_argument('--status', choices=('working', 'stopped', 'done'), required=True)
    for arg in ('task', 'stop', 'next', 'entry'):
        update.add_argument('--' + arg, required=True)
    update.add_argument('--artifact', help='local path or external snapshot reference for the next session')
    update.add_argument('--evidence', help='last passing evidence path or receipt reference')
    actions.add_parser('list').add_argument('--task')
    subs.add_parser('lint')
    tidy = subs.add_parser('tidy', help='remove template maintainer files an older install left in this project')
    tidy.add_argument('--dry-run', action='store_true')
    tidy.add_argument('--force', action='store_true', help='also remove maintainer files that differ from this release')
    install = subs.add_parser('install')
    install.add_argument('--target', type=Path, required=True)
    install.add_argument('--dry-run', action='store_true')
    install.add_argument('--merge', action='store_true', help='merge an existing AGENTS.md, CLAUDE.md and .gemini/settings.json')
    install.add_argument('--allow-modified', action='store_true')
    install.add_argument('--diff', action='store_true', help='with --dry-run, print each merge as a diff')
    doctor = subs.add_parser('doctor', help='hooks, interpreter, session identity and tool files at a glance')
    doctor.add_argument('--json', action='store_true')
    up = subs.add_parser('upgrade', help='bring a project to this template version; run from the new template folder')
    up.add_argument('--target', type=Path)
    up.add_argument('--dry-run', action='store_true', help='show the plan and write nothing')
    up.add_argument('--force', action='store_true', help='upgrade although a session works, or roll back past its writes')
    up.add_argument('--reason', help='what the user said, for --force and --overwrite-modified-tools')
    up.add_argument('--assume-base', type=Path, metavar='PACKAGE', help='the older release, a folder or zip, when the '
                    'project has no MANIFEST.json')
    up.add_argument('--no-hooks', action='store_true', help='leave hook settings as they are and list the stale ones')
    up.add_argument('--overwrite-modified-tools', action='store_true', help='back up and replace tool code the project '
                    'changed; needs --reason')
    up.add_argument('--rollback', metavar='NAME', help='put back the files of the upgrade folder NAME')
    up.add_argument('--scan', type=Path, metavar='FOLDER', help='list the workspaces under FOLDER (read-only)')
    up.add_argument('--depth', type=int, default=3)
    export = subs.add_parser('export')
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--allow-modified', action='store_true')
    mig = subs.add_parser('migrate')
    mig.add_argument('--target', type=Path, required=True, help='the continuity.v2 project to convert')
    mig.add_argument('--dry-run', action='store_true')
    mig.add_argument('--force', action='store_true', help='migrate even though a v2 writer still holds the workspace')
    rel = subs.add_parser('release')
    rel.add_argument('--keep-old', action='store_true', help='keep packages of earlier versions in dist/')
    rel.add_argument('--skip-full', metavar='REASON', help='release without a passing full self-test run on this code; '
                     'the reason is printed in dist/README.md')
    subs.add_parser('stamp')
    return p
