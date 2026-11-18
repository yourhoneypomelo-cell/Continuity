"""Decision-aware handoffs and optional, task-owned batch recovery notes."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import logs, tables
from .core import WorkspaceError, card, card_text, now, read, safe_path, sha, state_of, write
from .locks import lock
from .permits import permit
from .redaction import redact_pasted
from .schema import HANDOFF, TABLES

BATCHES = 'docs/state/BATCHES.json'
LINKS = 'docs/logs/DECISION_LINKS.json'


def _rows(root, rel):
    if not safe_path(root, rel).is_file():
        return []
    data = json.loads(read(root, rel))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise WorkspaceError(f'invalid records: {rel}')
    return data


def _json(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def digests(rows):
    return {r['ID']: sha(json.dumps(r, sort_keys=True).encode()) for r in rows}


def signature(rows):
    return sha(json.dumps(digests(rows), sort_keys=True).encode())


def changed(rows, cp, state):
    if state.get('handoff_review') == signature(rows):
        return []
    prior = (cp or {}).get('decision_digests')
    if prior is None:
        ledger = (cp or {}).get('ledger') or {}
        delta = [r['ID'] for r in rows if r['Status'] != ledger.get(r['ID'])]
    else:
        delta = [rid for rid, value in digests(rows).items() if prior.get(rid) != value]
    return list(dict.fromkeys([*((cp or {}).get('handoff_pending') or []), *delta]))


def confirm_next(root, state):
    state['handoff_review'] = signature(tables.rows(root, TABLES['decisions']))


def risk_observation(root, state, fields, until):
    value = fields.get('risks', card(root).get('risks'))
    if until:
        try:
            expiry = datetime.fromisoformat(until.replace('Z', '+00:00'))
            if not expiry.tzinfo or not value or value == 'none':
                raise ValueError
        except ValueError:
            raise WorkspaceError('--risk-until needs a dated time with UTC offset and a recorded risk') from None
        state['risk_observation'] = {'risk': sha(value.encode()), 'observed_at': now(), 'until': expiry.isoformat()}
    elif 'risks' in fields and fields['risks'] != card(root).get('risks'):
        state.pop('risk_observation', None)


def decision_changes(root, state, t, row, changes, message, supersedes, next_step, observed=None, artifact=None):
    """Prepare all linked records while the caller holds the same owner lock."""
    if not any((message, supersedes, next_step, observed, artifact)):
        return
    rid = row['ID']
    if message:
        from . import reconcile
        if message not in {mid for mid, _, _ in reconcile.user_messages(root)}:
            raise WorkspaceError('unknown captured user message; run ws reconcile --review')
        prior = reconcile.accounted(root).get(message, {}).get('Outcome', '')
        ids = re.findall(r'\b[RQPFDT][1-9]\d*\b', prior) if not prior.startswith('no record:') else []
        if rid not in ids:
            rel = logs.path_of(reconcile.LOG)
            changes[rel] = logs.add(logs._text(root, reconcile.LOG), reconcile.LOG,
                                    {'Message': message, 'Outcome': ', '.join([*ids, rid])})
    if t.key != 'decisions':
        if supersedes or next_step or observed or artifact:
            raise WorkspaceError('--supersedes, --next, --observed and --artifact apply to decisions')
        return
    if (supersedes or next_step) and row['Status'] != 'adopted':
        raise WorkspaceError('adopt the new decision before replacing another decision or changing the next step')
    old_ids = list(dict.fromkeys(i for value in supersedes or [] for i in re.split(r'[,\s]+', value.upper()) if i))
    existing = {r['ID']: r for r in tables.rows(root, t)}
    for old in old_ids:
        if (old in existing and existing[old]['Status'] == 'superseded'
                and existing[old]['Reason'].startswith(f'Superseded by {rid}.')):
            continue
        if old == rid or old not in existing or existing[old]['Status'] != 'adopted':
            raise WorkspaceError(f'{old} must be a different, currently adopted decision')
        replaced = {**existing[old], 'Status': 'superseded', 'Reason': f'Superseded by {rid}. ' + existing[old]['Reason']}
        changes[t.file] = tables.upsert(changes[t.file], t.headers, t.file, replaced)
        rel = logs.path_of(t.log)
        changes[rel] = logs.add(changes.get(rel) or read(root, rel), t.log, {
            'ID': old, 'Event': 'adopted -> superseded', 'Detail': f'Superseded by {rid}', 'Source': message or row['Source']})
    step = redact_pasted(' '.join((next_step or '').split()))
    if next_step is not None and not step:
        raise WorkspaceError('--next needs a concrete step')
    if step:
        permit(state, 'card')
        changes[HANDOFF] = card_text(read(root, HANDOFF), {'next_step': step})
    links = _rows(root, LINKS)
    link = {'decision': rid, 'message': message or '', 'supersedes': old_ids, 'next': step}
    for key, value in (('observed', observed), ('artifact', artifact)):
        if value:
            link[key] = redact_pasted(' '.join(value.split()))
    if not links or any(links[-1].get(k) != v for k, v in link.items()):
        changes[LINKS] = _json([*links, {**link, 'at': now()}])


def previous_add(root, t, row, message, supersedes, next_step, observed, artifact):
    """A replay of a captured decision must not add a row or reset a later handoff."""
    if not message or t.key != 'decisions':
        return None
    requested = {i for arg in supersedes or [] for i in re.split(r'[,\s]+', arg.upper()) if i}
    step = redact_pasted(' '.join((next_step or '').split()))
    known = {r['ID']: r for r in tables.rows(root, t)}
    for link in reversed(_rows(root, LINKS)):
        old = known.get(link.get('decision'))
        if (link.get('message') == message and old and old[t.summary] == row[t.summary]
                and set(link['supersedes']) == requested and link['next'] == step
                and all(link.get(k, '') == redact_pasted(' '.join((v or '').split())) for k, v in
                        (('observed', observed), ('artifact', artifact)))
                and old['Source'] == row['Source'] and old['Reason'] == row['Reason']):
            return old['ID']
    return None


def _recent_decisions(root, rows, delta):
    adopted = {r['ID']: r for r in rows if r['Status'] == 'adopted'}
    pending = {rid: adopted[rid] for rid in delta if rid in adopted}
    candidates = (pending or adopted).copy()
    if not candidates:
        return [], False
    limit = min(3 if pending else 1, len(candidates))
    chosen = []
    for event in logs.newest_first(root, 'CHANGE_LOG'):
        row = candidates.pop(event['ID'], None)
        if row is not None:
            chosen.append(row)
            if len(chosen) == limit:
                return chosen, True
    # Hand-edited or imported rows can lack an event. Their IDs and disk times cannot date the change.
    return (chosen + list(candidates.values()))[:3], False


def decision_lines(root, rows, cp, state):
    delta = changed(rows, cp, state)
    links = _rows(root, LINKS)
    chosen, ordered = _recent_decisions(root, rows, delta)
    lines = []
    for row in chosen[:3]:
        rid = row['ID']
        detail = {}
        for link in links:
            if link.get('decision') == rid:
                detail.update({k: v for k, v in link.items() if v})
        origin = ' / '.join(filter(None, [detail.get('message'), ', '.join(detail.get('supersedes') or [])]))
        lines.append(f'- {rid} adopted: {row["Decision"][:300]}' + (f' (source / supersedes: {origin})' if origin else ''))
        if detail.get('observed'):
            lines.append('  Observed: ' + detail['observed'][:240])
        if detail.get('artifact'):
            lines.append('  Evidence: ' + detail['artifact'][:200])
    if delta:
        lines.append('Review the handoff against changed decisions: ' + ', '.join(delta[-8:]) + '.')
    title = '## Latest decision' if ordered else '## Decisions (change order unavailable)'
    return (['', title, '', *lines] if lines else []), delta


def risk_label(state, value):
    if state.get('resolved_risk') == sha(value.encode()):
        return ' (closed)'
    item = state.get('risk_observation') or {}
    if item.get('risk') != sha(value.encode()) or not item.get('until'):
        return ''
    expired = datetime.now(timezone.utc) >= datetime.fromisoformat(item['until'])
    return f' (observed {item["observed_at"]}, {"expired" if expired else "valid until"} {item["until"]})'


BATCH_STATE = ('status', 'stop', 'next', 'entry', 'evidence', 'artifact', 'at')


def _batch_state(row):
    return (isinstance(row, dict) and all(isinstance(row.get(k), str) for k in BATCH_STATE)
            and row['status'] in ('working', 'stopped', 'done'))


def batches(root):
    rows = _rows(root, BATCHES)
    for row in rows:
        history = row.get('history', [])
        if (not _batch_state(row) or any(not isinstance(row.get(k), str) for k in ('task', 'name'))
                or not isinstance(history, list) or not all(_batch_state(old) for old in history)):
            raise WorkspaceError(f'invalid batch record in {BATCHES}')
    return rows


def batch_command(root: Path, args):
    if args.action == 'list':
        rows = [r.copy() for r in batches(root) if not args.task or r['task'] == args.task]
        for row in rows:
            if args.history:
                row.setdefault('history', [])
            else:
                row.pop('history', None)
        print(_json(rows), end='')
        return 0
    from .ops import bump, require_owner
    from .taskproofs import task_rows
    with lock(root):
        state = state_of(root)
        require_owner(root, state, args.writer, args.rev)
        permit(state, 'task', [args.task], what='update batches for')
        if args.task not in task_rows(root):
            raise WorkspaceError(f'unknown task {args.task}')
        row = {k: redact_pasted(' '.join((getattr(args, k) or '').split()))
               for k in ('task', 'name', 'status', 'stop', 'next', 'entry', 'evidence', 'artifact')}
        if any(not row[k] for k in ('name', 'stop', 'next', 'entry')):
            raise WorkspaceError('give the batch name, stop point, next step and restart entry')
        rows = batches(root)
        prior = next((r for r in rows if (r['task'], r['name']) == (row['task'], row['name'])), None)
        if prior:
            for key in ('evidence', 'artifact'):
                if getattr(args, key) is None:
                    row[key] = prior[key]
        if not prior or any(prior[k] != v for k, v in row.items()):
            if prior:
                row['history'] = [*prior.get('history', []), {k: prior[k] for k in BATCH_STATE}]
                rows.remove(prior)
            rows.append({**row, 'at': now()})
            write(root, BATCHES, _json(rows))
            bump(root, state)
    print(f'{args.task} batch {row["name"]}: {row["status"]}')
    return 0


def batch_lines(root, task_rows):
    rows = batches(root)
    if not rows:
        return []
    open_tasks = {r['ID'] for r in task_rows if r['Status'] not in TABLES['tasks'].closed}
    pending = [r for r in reversed(rows) if r['task'] in open_tasks and r['status'] != 'done']
    if not pending:
        return ['', f'## Batch history ({len(rows)}; ws batch list --history)', '', 'No open task has a batch to resume.']
    stopped = [r for r in pending if r['status'] == 'stopped']
    shown = (stopped or pending)[:3]
    lines = ['', f'## Batch recovery ({len(rows)}; {BATCHES}; ws batch list)', '']
    for r in shown:
        lines.append(f'- {r["task"]} {r["name"]} ({r["status"]}): {r["stop"][:130]} | next: {r["next"][:130]}'
                     f' | entry: {r["entry"][:160]}' + (f' | evidence: {r["evidence"][:130]}' if r['evidence'] else '')
                     + (f' | artifact: {r["artifact"][:160]}' if r['artifact'] else ''))
    return lines
