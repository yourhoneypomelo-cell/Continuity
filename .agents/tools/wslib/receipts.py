"""Link external results to exact local bytes without contacting the external service."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

from . import sharecheck
from .core import WorkspaceError, card, card_text, checkpoint_of, now, read, safe_path, sha, state_of, write
from .locks import lock
from .redaction import redact_pasted
from .schema import HANDOFF

FILE = 'docs/logs/DELIVERY_RECEIPTS.json'
DIGEST = re.compile(r'[0-9a-f]{64}')
FIELDS = ('task', 'scope', 'ref', 'result', 'file', 'sha256', 'candidate', 'container', 'member', 'container_sha256', 'at')


class ReceiptMismatch(WorkspaceError):
    exit_code = 1


def _digest(stream) -> str:
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(chunk)
    return result.hexdigest()


def _file_digest(root, rel):
    with safe_path(root, rel).open('rb') as stream:
        return _digest(stream)


def _key(row):
    return row['task'], row['scope'], row['ref']


def _stamp(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()


def records(root: Path, cp=None) -> list:
    path = safe_path(root, FILE)
    rows = json.loads(read(root, FILE)) if path.is_file() else []
    if not isinstance(rows, list):
        raise WorkspaceError(f'invalid receipt list in {FILE}')
    for row in rows:
        if (not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in FIELDS)
                or not all(row[k] for k in ('scope', 'ref', 'result', 'file', 'candidate', 'at'))
                or not re.fullmatch(r'T[1-9]\d*', row['task']) or not DIGEST.fullmatch(row['sha256'])
                or bool(row['member']) != bool(row['container'])
                or (row['container'] and not DIGEST.fullmatch(row['container_sha256']))):
            raise WorkspaceError(f'invalid delivery receipt in {FILE}')
    if len({_key(row) for row in rows}) != len(rows):
        raise WorkspaceError(f'duplicate delivery receipt in {FILE}')
    if cp is None:
        cp = checkpoint_of(root, state_of(root))
    sealed = (cp or {}).get('receipt_history') or []
    if [_stamp(r) for r in rows[:len(sealed)]] != sealed:
        raise WorkspaceError(f'sealed delivery receipt history changed in {FILE}')
    return rows


def anchors(rows):
    return [_stamp(row) for row in rows]


def current(rows, tasks=None):
    latest = {}
    for row in rows:
        if tasks is None or row['task'] in tasks:
            latest[row['task'], row['scope']] = row
    return list(latest.values())


def proof_bindings(rows):
    result = {}
    for row in rows:
        result.setdefault(row['task'], {})[row['scope']] = {'ref': row['ref'], 'sha256': row['sha256'],
                                                            'record': _stamp(row)}
    return result


def proof_problem(proof, rid, bindings):
    if (proof.get('delivery_receipts') or {}).get(rid, {}) != bindings.get(rid, {}):
        return f'{rid}: acceptance does not cover the current delivery receipt; run ws verify {rid} again'
    return ''


def _receipt_file(root, rel):
    path = safe_path(root, rel)
    if not rel.strip() or not path.is_file():
        raise WorkspaceError(f'delivery file missing: {rel}')
    return path


def problems(root, row, candidate=None):
    paths = dict.fromkeys((row['file'], candidate or row['candidate']))
    try:
        for rel in paths:
            _receipt_file(root, rel)
            actual = _file_digest(root, rel)
            if actual != row['sha256']:
                raise WorkspaceError(f'{rel} SHA-256 {actual}; expected {row["sha256"]}')
        if row['container']:
            path = _receipt_file(root, row['container'])
            if _file_digest(root, row['container']) != row['container_sha256']:
                raise WorkspaceError(f'{row["container"]} differs from the recorded container')
            with zipfile.ZipFile(path) as bundle:
                members = [m for m in bundle.infolist() if m.filename == row['member']]
                if len(members) != 1 or members[0].is_dir():
                    raise WorkspaceError('the delivery archive must contain exactly one member at the recorded path')
                if members[0].file_size != safe_path(root, row['file']).stat().st_size:
                    raise WorkspaceError('the delivery archive member has a different size')
                with bundle.open(members[0]) as stream:
                    if _digest(stream) != row['sha256']:
                        raise WorkspaceError('the delivery archive member has a different SHA-256')
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as error:
        return f'{row["task"]} receipt {row["ref"]} ({row["scope"]}): {error}'
    return ''


def failures(root, rows):
    return [(row['task'], reason) for row in rows if (reason := problems(root, row))]


def checked(root, ids):
    rows = current(records(root), ids) if ids else []
    errors = failures(root, rows)
    if errors:
        raise ReceiptMismatch('\n'.join(reason for _, reason in errors))
    return rows


def _close_risk(root, row, state):
    old = row.get('resolved_risk')
    if not old or old['revision'] != state['revision'] or sha(card(root)['risks'].encode()) != old['digest']:
        return False
    summary = f'Closed by {row["task"]} receipt {row["ref"]} ({row["scope"]}) at {row["at"]}. History: {FILE}'
    write(root, HANDOFF, card_text(read(root, HANDOFF), {'risks': summary}))
    state.pop('risk_observation', None)
    state['resolved_risk'] = sha(summary.encode())
    return True


def record(root, args):
    from .ops import bump, require_owner
    from .permits import permit
    from .taskproofs import task_rows
    with lock(root):
        state = state_of(root)
        require_owner(root, state, args.writer, args.rev)
        permit(state, 'task', [args.task], what='record a receipt for')
        if args.task not in task_rows(root):
            raise WorkspaceError(f'unknown task {args.task}')
        if bool(args.container) != bool(args.member) or (args.container_sha256 and not args.container):
            raise WorkspaceError('--container and --member belong together; --container-sha256 needs both')
        row = {key: (getattr(args, key, None) or '').strip() for key in FIELDS}
        row.update(candidate=row['candidate'] or row['file'], sha256=row['sha256'].lower(), at=now())
        for key in ('ref', 'scope', 'result'):
            row[key] = redact_pasted(' '.join(row[key].split()))
            if not row[key]:
                raise WorkspaceError(f'--{key} needs a value')
        for key in ('file', 'candidate', 'container', 'member'):
            if redact_pasted(row[key]) != row[key]:
                raise WorkspaceError(f'--{key} looks like it includes a credential')
        if not DIGEST.fullmatch(row['sha256']):
            raise WorkspaceError('--sha256 needs the independently approved 64-digit SHA-256')
        safe_path(root, row['candidate'])
        if row['container']:
            member = PurePosixPath(row['member'])
            if member.is_absolute() or '..' in member.parts or '\\' in row['member']:
                raise WorkspaceError('give an exact relative --member path in the ZIP')
            row['container_sha256'] = row['container_sha256'].lower() or _file_digest(root, row['container'])
        error = problems(root, row, row['file'])
        if error:
            raise ReceiptMismatch(error)
        rows = records(root)
        existing = next((r for r in rows if _key(r) == _key(row)), None)
        if existing:
            if any(existing[k] != row[k] for k in FIELDS if k != 'at'):
                raise WorkspaceError('this task, scope and receipt reference already identify a different record')
            if args.resolve_risk:
                permit(state, 'card')
                if not existing.get('resolved_risk'):
                    raise WorkspaceError('receipt already recorded; use ws card to update the current risk')
                if _close_risk(root, existing, state):
                    bump(root, state)
            return existing
        sharecheck.require_clean(sharecheck.inspect(root, row['container'] or row['file']))
        if args.resolve_risk:
            permit(state, 'card')
            old = card(root)['risks']
            row['resolved_risk'] = {'text': redact_pasted(old), 'digest': sha(old.encode()), 'revision': state['revision'],
                                    'observation': state.get('risk_observation') or {}}
        rows.append(row)
        write(root, FILE, json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        _close_risk(root, row, state)
        bump(root, state)
        return row


def command(root, args):
    if args.action == 'audit':
        report = sharecheck.inspect(root, args.path)
        print(json.dumps(report, ensure_ascii=False))
        return int(bool(report['findings']))
    if args.action == 'record':
        row = record(root, args)
        print(f'Recorded {row["task"]} receipt {row["ref"]}, scope {row["scope"]}: {row["result"]}')
        error = problems(root, row)
        if error:
            print(error)
        return int(bool(error))
    rows = records(root)
    if args.task:
        rows = [r for r in rows if r['task'] == args.task]
    if args.action == 'list':
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    rows = [r for r in rows if r['ref'] == args.ref] if args.ref else current(rows)
    if not rows:
        raise WorkspaceError('no matching delivery receipt')
    failed = False
    for row in rows:
        error = problems(root, row, args.file)
        failed |= bool(error)
        print(error or f'{row["task"]} receipt {row["ref"]} matches: {row["scope"]} — {row["result"]}')
    return int(failed)
