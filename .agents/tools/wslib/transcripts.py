"""Durable visible turns shared by transcript import and prompt hooks."""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from pathlib import Path

from . import origin
from .core import atomic_write, safe_path, sha
from .messages import ENTRY_RE, ID_RE, STAMP_RE, after, carry, new_id, old_id
from .redaction import redact, redact_pasted
from .schema import HEADING_NOTE

HEADING_RE = re.compile(r'^(## \d+\. (?:user|assistant)' + HEADING_NOTE + r')[ \t]*$', re.M)
PENDING_RE = re.compile(r'^<!-- WS-HOOK-PENDING: (m[0-9a-f]+(?: m[0-9a-f]+)*) -->$', re.M)
HOST_IDS_RE = re.compile(r'^<!-- WS-HOST-IDS: (\{[^\n]*\}) -->$', re.M)
EDIT_RE = re.compile(r'^<!-- WS-SOURCE-EDIT: ([0-9a-f]{64}) -->$', re.M)
MAX_MESSAGE = 200_000
VISIBLE_MARK = '<!-- WS-VISIBLE: 2 -->'


def escape_headings(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if len(text) > MAX_MESSAGE:
        text = text[:MAX_MESSAGE] + f'\n\n[truncated: the message had {len(text)} characters]'
    return HEADING_RE.sub(r' \1', text)


@dataclass(frozen=True)
class Turn:
    role: str
    body: str
    note: str
    mid: str
    pending: bool = False
    source_id: str = ''


def source_edit(text: str) -> str:
    mark = EDIT_RE.search(text.partition('\n## ')[0])
    return mark[1] if mark else ''


def saved(text: str, rel: str) -> list:
    header = text.split('\n## ', 1)[0]
    pending = PENDING_RE.search(header)
    pending_ids = set(pending[1].split()) if pending else set()
    mark = HOST_IDS_RE.search(header)
    ids = json.loads(mark[1]) if mark else {}
    result = []
    for row in ENTRY_RE.finditer(text):
        role, note, body = row[2], row[3], row[4].strip()
        stored = ID_RE.search(note)
        mid = stored[1] if stored else (old_id(body) if role == 'user' else new_id(rel + '#assistant', int(row[1]), body))
        # Compute legacy IDs from the original before sanitising material that may be copied into a revision.
        body = redact_pasted(body) if role == 'user' else redact(body)
        source_id = ids.get(mid, '')
        result.append(Turn(role, body, redact(ID_RE.sub('', note).strip()), mid, mid in pending_ids,
                           source_id if isinstance(source_id, str) and redact_pasted(source_id) == source_id else ''))
    return result


def incoming(old: list, rel: str, messages: list) -> list:
    turns = []
    for role, text, *note in messages:
        body = (redact_pasted(text) if role == 'user' else redact(text)).strip()
        turns.append(Turn(role, body, note[0] if note else '', '', source_id=note[1] if len(note) > 1 else ''))
    ids = {}
    for role in ('user', 'assistant'):
        subset = [(i, escape_headings(t.body), t.source_id) for i, t in enumerate(turns, 1) if t.role == role]
        ids[role] = iter(carry(old, rel, subset, role))
    return [replace(t, mid=next(ids[t.role])) for t in turns]


def markdown(host, session, turns, source, *, history=False, edit='', storage=None):
    lines = [f'# Transcript {host} {session}', '', f'Source: {source}. Visible user and assistant text, redacted.',
             'Times are UTC where known. Hook-only times record observation. A missing time or recipient receipt is unknown.']
    lines.append(VISIBLE_MARK)
    pending = [t.mid for t in turns if t.pending]
    if pending:
        lines.append('<!-- WS-HOOK-PENDING: ' + ' '.join(pending) + ' -->')
    ids = {t.mid: t.source_id for t in turns if t.source_id}
    if ids:
        lines.append('<!-- WS-HOST-IDS: ' + json.dumps(ids, separators=(',', ':')) + ' -->')
    if edit:
        lines.append('<!-- WS-SOURCE-EDIT: ' + edit + ' -->')
    if history:
        lines.append(f'Earlier visible revisions: docs/chats/{storage or host}/raw/revisions/{session}/')
    if turns and turns[-1].role == 'user':
        lines.append('No assistant reply after the last observed user message is present in this capture.')
    lines.append('')
    for number, turn in enumerate(turns, 1):
        suffix = (' ' + turn.note if turn.note else '') + f' [{turn.mid}]'
        lines += [f'## {number}. {turn.role}{suffix}', '', escape_headings(turn.body), '']
    return '\n'.join(lines)


def rewrite(root: Path, rel: str, host: str, session: str, messages: list, source: str, since=None, edit='', cursor=False, actual_host=None) -> list:
    """Merge a host snapshot with hook turns that it has not flushed yet. Called under the workspace lock."""
    path = safe_path(root, rel)
    old_text = path.read_text(encoding='utf-8') if path.is_file() else ''
    prior = saved(old_text, rel)
    if cursor and VISIBLE_MARK not in old_text.partition('\n## ')[0]:
        prior = [t for t in prior if t.role != 'user' or origin.classify(t.body, True, legacy=True)[0] == 'human']
    if since is not None and prior:
        allowed = after([(t.role, t.mid, t.note) for t in prior], since) or []
        keep = {mid for _, mid, _ in allowed}
        prior = [t for t in prior if t.mid in keep]
    previous_edit = source_edit(old_text)
    fresh = incoming(prior, rel, messages)
    old_ids, new_ids = [t.mid for t in prior], [t.mid for t in fresh]
    explicit_edit = bool(edit and edit != previous_edit)
    if not explicit_edit and len(fresh) < len(prior) and old_ids[:len(fresh)] == new_ids:
        fresh.extend(prior[len(fresh):])
    else:
        observed = set(new_ids)
        for index, turn in enumerate(prior):
            if not turn.pending or turn.mid in observed:
                continue
            # A substantive extension at the same position has its own ID. The shorter text survives in history.
            successor = fresh[index] if index < len(fresh) else None
            if successor and successor.role == turn.role and successor.body.startswith(turn.body):
                continue
            fresh.append(turn)
    current = {t.mid for t in fresh}
    archive = safe_path(root, f'docs/chats/{host}/raw/revisions/{session}')
    if prior and any(t.mid not in current for t in prior):
        previous = markdown(actual_host or host, session, prior, 'previous visible capture')
        archive_rel = archive / (sha(previous.encode('utf-8')) + '.md')
        if not archive_rel.exists():
            atomic_write(archive_rel, previous)
    if fresh or (explicit_edit and prior):
        text = markdown(actual_host or host, session, fresh, source, history=archive.is_dir(),
                        edit=edit or previous_edit, storage=host)
        if text != old_text:
            atomic_write(path, text)
    return fresh


def visible_copy(turns: list, suffix: str) -> str:
    """Export only the public conversation fields, regardless of secrets policy or host record format."""
    rows = []
    for turn in turns:
        stamp = STAMP_RE.search(turn.note)
        rows.append({'id': turn.mid, 'source_id': turn.source_id or None, 'role': turn.role, 'content': turn.body, 'timestamp': stamp[0] if stamp else None,
                     'time_source': ('hook' if turn.pending else 'host') if stamp else 'unknown',
                     'delivery': 'receipt unknown' if turn.role == 'assistant' else 'observed'})
    if suffix.lower() == '.json':
        return json.dumps(rows, ensure_ascii=False) + '\n'
    return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
