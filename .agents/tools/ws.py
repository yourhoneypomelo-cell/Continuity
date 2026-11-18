"""Workspace continuity tool. Run "python .agents/tools/ws.py --help" for the command list."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

if sys.version_info < (3, 9):  # before wslib, which needs 3.9; this file keeps to the 3.7 grammar
    print(f'ERROR: ws.py needs Python 3.9 or newer, and {sys.executable} is Python '
          f'{".".join(map(str, sys.version_info[:3]))}. Run it with a newer one, for example '
          '"python3.12 .agents/tools/ws.py ...". For hooks: ws hooks enable <host> --python python3.12', file=sys.stderr)
    if '--hook' in sys.argv or sys.argv[1:2] == ['capture']:  # a hook must never break the host session
        host = sys.argv[sys.argv.index('--hook') + 1] if '--hook' in sys.argv[:-1] else ''
        print({'kiro': '', 'cursor': '{"continue": true}'}.get(host, '{}'))
        sys.exit(0)
    sys.exit(2)

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wslib import capture, distribution, lint, migrate, ops, validate  # noqa: E402
from wslib.core import READ_ONLY, WorkspaceError, configure_stdout, session_key  # noqa: E402

READ_ONLY_COMMANDS = ('brief', 'turn', 'status', 'check', 'lint', 'doctor')
from wslib.hooks import (  # noqa: E402,F401  (the tests use hook_settings, _commands, _is_ours, interpreter)
    CLAUDE_SHAPED, HOSTS, _commands, _is_ours, disable_hooks, enable_hooks, hook_settings, interpreter,
)
from wslib.cli import COMMANDS, parser  # noqa: E402,F401
from wslib.schema import VERSION  # noqa: E402,F401

TOOL = Path(__file__).resolve()
TEMPLATE_ROOT = TOOL.parents[2]


def read_stdin() -> str:
    """Hosts send UTF-8 JSON. Read bytes so the Windows console code page cannot garble it."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return ''
        data = sys.stdin.buffer.read()
    except (OSError, ValueError, AttributeError):
        return ''
    for encoding in ('utf-8-sig', 'utf-16'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def hook_brief(root: Path, host: str):
    """SessionStart hook: print the brief in the format the host injects into context."""
    try:
        payload = json.loads(read_stdin() or '{}')
        raw = capture._first(payload, capture.SESSION_KEYS) if isinstance(payload, dict) else None
    except ValueError:
        raw = None
    try:
        text = ops.brief(root, session_key(raw) if raw else None)
    except Exception as error:  # a hook must never break the host session
        text = f'Workspace brief unavailable ({error}). Read AGENTS.md and run: python .agents/tools/ws.py check'
    text = ('The workspace brief below was printed by ws brief at session start, so step 1 of "Start of every session" '
            'is done. Do not run ws brief again; continue with step 2.\n\n') + text
    if len(text) > BRIEF_LIMIT:
        # Claude Code saves longer hook output to a file and shows the model only a preview.
        text = cut_brief(text, BRIEF_LIMIT - 200)
    if host in ('claude', 'gemini', 'codex', *CLAUDE_SHAPED):
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': text}}))
    elif host == 'antigravity':
        print(json.dumps({'injectSteps': [{'systemMessage': {'systemMessage': text}}]}))
    elif host == 'cursor':
        print(json.dumps({'additional_context': text}))
    elif host == 'copilot':
        print(json.dumps({'additionalContext': text}))
    else:
        print(text)


BRIEF_LIMIT = 9000


def cut_brief(text: str, limit: int) -> str:
    """Shorten a brief for a hook. The Next section holds the start command and session key, so it is kept and
    the sections before it lose their tails first."""
    note = '\n[Brief cut. Run: python .agents/tools/ws.py brief]\n'
    head, sep, tail = text.partition('\n## Next\n')
    tail = sep + tail if sep else ''
    room = max(limit - len(tail) - len(note), 0)
    return head[:room].rsplit('\n', 1)[0] + '\n' + note + tail
COMPACTED = '.agents/cache/compacted'
# Hosts whose session start hook does not run again after compaction; their next per-turn hook adds the brief.
REBRIEF_AFTER_COMPACT = ('gemini', 'antigravity', 'cursor')

TURN_EVENTS = {'claude': 'UserPromptSubmit', 'codex': 'UserPromptSubmit', 'gemini': 'BeforeAgent',
               **{name: 'UserPromptSubmit' for name in CLAUDE_SHAPED}}


def taken_over(root: Path, payload, host: str) -> str:
    """The hook payload names this conversation. When the workspace was claimed with another conversation's brief key,
    or on Cursor under another CURSOR_CONVERSATION_ID, tell this one to stop writing before it does anything. Cursor's
    conversation_id is that variable's value; other hosts' payload ids are not known to match their variables."""
    try:
        raw = capture._first(payload, capture.SESSION_KEYS) if isinstance(payload, dict) else None
        if not raw:
            return ''
        from wslib.core import session_key, state_of
        state = state_of(root)
        owner = state.get('session') or {}
        if not state.get('writer') or owner.get('via') not in (('key', 'env') if host == 'cursor' else ('key',)):
            return ''
        mine = session_key(session_key(raw))
        claimed = {(c.get('session') or {}).get('id') for c in (state.get('claims') or {}).values() if not c.get('released_at')}
        if mine == owner.get('id') or mine in claimed:
            return ''
        return (f'Workspace: {state["writer"]} took over this workspace in another conversation. Do not write with ws '
                'or edit files; tell the user, re-read docs/state/HANDOFF.md, and continue only if the user says this '
                'conversation should take it back with ws start.')
    except Exception:  # a hook must never break the host session
        return ''


def hook_turn(root: Path, host: str):
    """Prompt-submit hook: remind the agent to record before acting. Silent on any failure."""
    raw = read_stdin()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    if host == 'antigravity' and isinstance(payload, dict) and payload.get('invocationNum', 0) != 0:
        # PreInvocation fires before every model call; remind only before the first one.
        print('{}')
        return
    saved = {}
    if isinstance(payload, dict):
        # Saved as it arrives, so this turn can reconcile it before its checkpoint; the Stop hook's copy keeps its ID.
        try:
            os.environ.setdefault('WS_LOCK_WAIT', '3')
            saved = capture.submit(root, host, payload)
        except Exception as error:  # a hook must never break the host session
            print(f'capture skipped: {str(error).splitlines()[0][:200]}', file=sys.stderr)
    kinds = []
    if isinstance(payload, dict):
        from wslib import nudge
        from wslib.coverage import credential_kinds
        prompt = capture._first(payload, capture.PROMPT_KEYS) or ''
        if prompt and not prompt.startswith(nudge.MESSAGE[:40]):
            # Only the reconciliable ID goes into a nudge marker, even when live chat capture is disabled.
            nudge.remember(root, host, capture.session_name(payload), saved.get('id', ''),
                           nudge.question_only(prompt))
        try:
            from wslib.core import CREDENTIALS
            kinds = credential_kinds(prompt) if prompt and CREDENTIALS.get() == 'ask' else []
        except Exception:  # a hook must never break the host session
            kinds = []
    try:
        text = ops.turn_context(root)
    except Exception:  # a hook must never break the host session
        text = ops.turn_reminder(root)
    if saved.get('id'):
        text += (f' This message is saved as {saved["id"]}: after recording what it asks for, run "ws reconcile '
                 f'{saved["id"]} --ids <rows>", or --reason "<why none>" if it needs no record.')
    try:
        from wslib.nudge import turn_mode, turn_record
        record = turn_record(root)
        text = text + ' ' + record if record else text
        raw = capture._first(payload, capture.SESSION_KEYS) if isinstance(payload, dict) else None
        said = capture._first(payload, capture.PROMPT_KEYS) if isinstance(payload, dict) else None
        mode = turn_mode(root, said or '', session_key(raw) if raw else None)
        text = mode + '\n\n' + text if mode else text
    except Exception:  # a hook must never break the host session
        pass
    taken = taken_over(root, payload, host)
    if taken:
        text = taken + '\n\n' + text
    if kinds:
        text = SECRET_AGENT.format(', '.join(kinds)) + '\n\n' + text
    marker = root / COMPACTED
    if host in REBRIEF_AFTER_COMPACT and marker.exists():
        try:
            marker.unlink()
            head = text + '\n\nThe context was compacted. Current workspace brief:\n\n'
            raw = capture._first(payload, capture.SESSION_KEYS) if isinstance(payload, dict) else None
            brief = ops.brief(root, session_key(raw) if raw else None)
            room = BRIEF_LIMIT - len(head) - 120
            if len(brief) > room:
                brief = cut_brief(brief, max(room, 0))
            text = head + brief
        except Exception:  # a hook must never break the host session
            pass
    shown = SECRET_USER.format(', '.join(kinds)) if kinds else ''
    if host in TURN_EVENTS:
        out = {'hookSpecificOutput': {'hookEventName': TURN_EVENTS[host], 'additionalContext': text}}
        print(json.dumps({**out, 'systemMessage': shown} if shown else out))
    elif host == 'antigravity':
        print(json.dumps({'injectSteps': [{'ephemeralMessage': text}]}))
    elif host == 'cursor':
        # Cursor drops additional_context longer than 10,000 characters.
        out = {'continue': True, 'additional_context': text[:BRIEF_LIMIT]}
        print(json.dumps({**out, 'user_message': shown} if shown else out))
    else:
        print(text)
        if shown:
            print(shown, file=sys.stderr)


# The credential notice of the prompt hook (B41). It names the kind of credential, never the value, and never blocks.
# It is sent only while the project has no credential rule; after the user decides, the rule speaks for itself.
SECRET_AGENT = ('This message contains a credential ({}). The project has no rule yet for keeping credentials. Use it '
                'for the task, but before writing it into a file, a command, a log or a commit, ask the user once how '
                'this project keeps credentials (as written in a file they name, in environment variables, or out of '
                'files), then record the answer: ws add preference and the WORKSPACE "credentials" setting.')
SECRET_USER = ('Workspace: this message contains a credential ({}). Until you decide how this project keeps credentials, '
               'the agent will ask before writing it anywhere, and saved transcripts are redacted.')


def autosave(root: Path):
    """Stop hook helper: an intermediate checkpoint when WORKSPACE sets "autosave": true and the state is valid.

    It never waits for a busy lock and never writes to stdout, because hosts read hook stdout as JSON."""
    from wslib.core import config, state_of
    previous = os.environ.get('WS_LOCK_WAIT')
    os.environ['WS_LOCK_WAIT'] = '0'
    try:
        if not config(root).get('autosave') or not state_of(root).get('writer'):
            return
        card_now = ops.card(root)
        with contextlib.redirect_stdout(io.StringIO()):
            ops.checkpoint(root, card_now.get('stop_point', 'autosave'), card_now.get('next_step', 'continue'), [], keep=True)
        print('autosave: checkpoint saved', file=sys.stderr)
    except Exception as error:  # never break the host; a refused autosave is fine
        print(f'autosave skipped: {str(error).splitlines()[0][:200]}', file=sys.stderr)
    finally:
        if previous is None:
            os.environ.pop('WS_LOCK_WAIT', None)
        else:
            os.environ['WS_LOCK_WAIT'] = previous


def find_root(start: Path | None) -> Path:
    """The project is the folder that holds this copy of ws.py, wherever the command runs from."""
    if start:
        return start.resolve()
    return TEMPLATE_ROOT


def linked_agents() -> str | None:
    """Where .agents points when it is a symbolic link or a junction: the project found from ws.py would be another."""
    agents = Path(os.path.abspath(__file__)).parents[1]
    try:
        linked = agents.is_symlink() or bool(getattr(os.lstat(agents), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return None
    return str(agents.resolve()) if linked else None


def main(argv=None) -> int:
    configure_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    rest = []
    if '--' in argv:
        index = argv.index('--')
        argv, rest = argv[:index], argv[index + 1:]
    args, extra = parser().parse_known_args(argv)
    if extra:
        hint = ''
        if '--set' in argv:
            hint = ('\nA --set value with spaces needs quotes: --set "requirement=Login works". '
                    'In PowerShell use single quotes around the whole field=value')
        print(f'ERROR: unexpected arguments: {" ".join(extra)}{hint}', file=sys.stderr)
        return 2
    if getattr(args, 'session', None):
        from wslib.core import GIVEN_SESSION
        GIVEN_SESSION.set(args.session)
    target = None if args.root else linked_agents()
    if target:
        print(f'ERROR: .agents in this project is a link to {target}, so ws.py would read and write that other '
              'project. Copy the .agents folder into this project instead of linking it', file=sys.stderr)
        if getattr(args, 'hook', None) or args.command == 'capture':  # a hook must never break the host session
            print({'kiro': '', 'cursor': '{"continue": true}'}.get(getattr(args, 'hook', None), '{}'))
            return 0
        return 2
    root = find_root(args.root)
    if args.command in READ_ONLY_COMMANDS or (args.command, getattr(args, 'action', None)) in (
            ('chats', 'audit'), ('batch', 'list'), ('receipt', 'list'), ('receipt', 'check')):
        READ_ONLY.set(True)  # the cache is not written; the turn hook still keeps its Stop-nudge marker
    try:
        from wslib.core import CREDENTIAL_FILES, CREDENTIALS, config
        settings = config(root)
        CREDENTIALS.set(settings['credentials'])
        CREDENTIAL_FILES.set(tuple(settings['credential_files']))
    except Exception:  # a broken or missing WORKSPACE block keeps the cautious default
        pass
    if getattr(args, 'hook', None) and args.command in ('brief', 'turn'):
        try:
            hook_brief(root, args.hook) if args.command == 'brief' else hook_turn(root, args.hook)
        except Exception as error:  # a hook must never break the host session
            print(f'hook skipped: {str(error).splitlines()[0][:200]}', file=sys.stderr)
            print({'kiro': '', 'cursor': '{"continue": true}'}.get(args.hook, '{}'))
        return 0
    try:
        if args.command == 'brief' and args.hook:
            hook_brief(root, args.hook)
        elif args.command == 'brief' and args.retired:
            from wslib.views import retired_list
            print(retired_list(root), end='')
        elif args.command == 'brief':
            print(ops.brief(root), end='')
        elif args.command == 'turn':
            if args.hook:
                hook_turn(root, args.hook)
            else:
                print(ops.turn_context(root))
        elif args.command == 'note':
            ops.note(root, ' '.join(args.text))
        elif args.command == 'idea':
            from wslib.rows import add_idea
            add_idea(root, ' '.join(args.text), args.writer, args.rev)
        elif args.command == 'status':
            print(json.dumps(ops.status(root), ensure_ascii=False, indent=2))
        elif args.command == 'check':
            errors = validate.validate(root, strict=args.strict, ready=args.ready, adapters=args.adapters)
            for warning in validate.advisories(root):
                print('WARNING: ' + warning)
            for error in errors:
                print('ERROR: ' + error)
            label = 'READY' if args.ready else 'PASS'
            print(f'Workspace: {"FAIL" if errors else label}')
            return 1 if errors else 0
        elif args.command == 'init':
            ops.init(root, args.goal, args.writer, args.session, args.chat_import, args.chats_git, args.chat_capture)
        elif args.command == 'start':
            ops.start(root, args.writer, args.force, args.reason, args.session, tasks=[t for v in args.task for t in v.replace(',', ' ').split()])
        elif args.command == 'add':
            ops.add(root, args.table, args.set, args.source, args.writer, args.rev, args.message, args.supersedes, args.next)
        elif args.command == 'set':
            ops.set_row(root, args.id, args.set, args.source, args.writer, args.rev, move_detail=args.move_detail,
                        message=args.message, supersedes=args.supersedes, next_step=args.next)
        elif args.command == 'receipt':
            from wslib import receipts
            return receipts.command(root, args)
        elif args.command == 'batch':
            from wslib.handover import batch_command
            return batch_command(root, args)
        elif args.command == 'card':
            ops.set_card(root, args.set, args.writer, args.rev, args.risk_until)
        elif args.command == 'goal':
            ops.set_goal(root, ' '.join(args.text), args.source, args.writer, args.rev)
        elif args.command == 'verify' and args.stale:
            if args.ids or rest or args.done or args.because:
                raise WorkspaceError('verify --stale takes no task IDs, command, --done or --because: it runs each '
                                     "stale task's own acceptance and keeps it done")
            return ops.verify_stale(root, args.timeout, args.writer, args.rev)
        elif args.command == 'verify':
            return ops.verify(root, args.ids, rest, args.done, args.kind, args.report, args.label, args.timeout, args.writer, args.rev,
                              args.because)
        elif args.command == 'checkpoint':
            ops.checkpoint(root, args.stop, args.next, args.set, args.keep, args.writer, args.rev, args.risk_until)
        elif args.command == 'compact':
            print(json.dumps(ops.compact(root, args.dry_run, args.prune_evidence, args.writer, args.rev), ensure_ascii=False, indent=2))
        elif args.command == 'snapshot':
            from wslib import snapshot
            result = snapshot.take(root, args.label, args.paths, args.pin)
            print(json.dumps(result, ensure_ascii=False))
            print(f'Saved. Nothing restores it in place: extract with "{result["extract"]}", compare, copy back by hand.')
        elif args.command == 'hooks' and args.action == 'disable':
            disable_hooks(root, args.host)
        elif args.command == 'hooks':
            enable_hooks(root, args.host, args.action == 'show', args.python, args.absolute)
        elif args.command == 'capture':
            # Hosts give hooks a few seconds; a busy workspace must not stall the host.
            os.environ.setdefault('WS_LOCK_WAIT', '3')
            payload = {}
            if args.event.lower() in ('precompact', 'precompress'):
                try:
                    (root / COMPACTED).parent.mkdir(parents=True, exist_ok=True)
                    (root / COMPACTED).write_text(args.host, encoding='utf-8')
                except OSError:
                    pass
            try:
                payload = json.loads(read_stdin() or '{}')
                result = capture.capture(root, args.host, args.event, payload if isinstance(payload, dict) else {})
            except Exception as error:  # a hook must never break the host session
                result = {'captured': False, 'reason': f'{type(error).__name__}: {error}'}
            print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
            if args.event in ('Stop', 'stop', 'agentStop', 'AfterAgent'):
                from wslib import nudge
                body = payload if isinstance(payload, dict) else {}
                text = nudge.check(root, body, capture.session_name(body)) if args.host != 'kiro' else None
                if text:
                    print(nudge.answer(args.host, text))
                    return 0
                autosave(root)
            return 0
        elif args.command == 'chats' and args.action == 'audit':
            from wslib.redaction import audit_chats
            report = audit_chats(root)
            print(json.dumps(report, ensure_ascii=False))
            return int(bool(report['findings']))
        elif args.command == 'chats':
            if not args.host:
                raise WorkspaceError('chats import needs a host')
            done = capture.import_sessions(root, args.host, None if args.all else capture.import_rule(root)[1])
            print(json.dumps(done, ensure_ascii=False))
            if done.get('untimed'):
                print('NOTE: ' + capture.UNTIMED.format(count=done['untimed'], host=args.host))
        elif args.command == 'reconcile':
            from wslib import reconcile
            if args.review:
                print('\n'.join(reconcile.review(root, args.last)) or 'No user message is saved in docs/chats/.')
            elif args.message:
                print(json.dumps(reconcile.mark(root, args.message, args.ids, args.reason, args.confirm), ensure_ascii=False))
            else:
                open_items, missing = reconcile.pending(root), reconcile.unlisted(root)
                if not open_items:
                    print('All user messages in the transcripts that docs/chats/INDEX.md lists are reconciled.' if missing
                          else 'All user messages in docs/chats/ are reconciled.')
                if missing:
                    print('WARNING: ' + reconcile.unlisted_text(missing))
                bodies = {}
                for mid, rel in open_items[:max(1, args.limit)]:
                    if rel not in bodies:
                        bodies[rel] = reconcile.texts(root / rel)
                    print(f'{mid}  {rel}\n    {" ".join(bodies[rel].get(mid, "").split())[:300]}')
                if len(open_items) > args.limit:
                    print(f'... and {len(open_items) - args.limit} more')
                if open_items:
                    print('\nFor each: ws reconcile <ID> --ids R4,P2   or   ws reconcile <ID> --reason "chat: greeting"')
        elif args.command == 'tidy':
            print(json.dumps(distribution.tidy(root, args.dry_run, args.force), ensure_ascii=False, indent=2))
        elif args.command == 'lint':
            issues = lint.run(root)
            for issue in issues:
                print(issue)
            print(f'Lint: {len(issues)} findings (advisory)')
        elif args.command == 'doctor':
            from wslib import doctor
            report = doctor.run(root)
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else doctor.render(report), end='')
            return 1 if report['problems'] else 0
        elif args.command == 'upgrade':
            from wslib import upgrade
            if args.scan:
                for line in upgrade.scan(TEMPLATE_ROOT, args.scan, args.depth):
                    print(json.dumps(line, ensure_ascii=False))
                return 0
            if not args.target:
                raise WorkspaceError('ws upgrade needs --target <project>, or --scan <folder>')
            if args.rollback:
                print(json.dumps(upgrade.rollback(args.target, args.rollback, args.force), ensure_ascii=False))
                return 0
            report = upgrade.run(TEMPLATE_ROOT, args.target, args.dry_run, args.force, args.reason, args.assume_base,
                                 args.no_hooks, args.overwrite_modified_tools)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1 if report['pending'] and not args.dry_run else 0
        elif args.command == 'install':
            result = distribution.install(TEMPLATE_ROOT, args.target, args.dry_run, args.merge, args.allow_modified,
                                          args.diff)
            diffs = result.pop('diff', {})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            for text in diffs.values():
                print(text)
            if args.dry_run and result['conflicts']:
                return 1
        elif args.command == 'export':
            print(json.dumps(distribution.export(TEMPLATE_ROOT, args.output, args.allow_modified), ensure_ascii=False, indent=2))
        elif args.command == 'migrate':
            print(json.dumps(migrate.migrate(TEMPLATE_ROOT, args.target, args.dry_run, args.force), ensure_ascii=False, indent=2))
        elif args.command == 'release':
            if root != TEMPLATE_ROOT or ops.status(root)['mode'] != 'bootstrap':
                raise WorkspaceError('release runs only in the template folder, which stays in bootstrap mode. '
                                     'A project folder cannot publish the template')
            print(json.dumps(distribution.release(TEMPLATE_ROOT, args.keep_old, args.skip_full), ensure_ascii=False, indent=2))
        elif args.command == 'stamp':
            print(json.dumps(distribution.stamp(TEMPLATE_ROOT), ensure_ascii=False))
    except (WorkspaceError, ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return getattr(error, 'exit_code', 2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
