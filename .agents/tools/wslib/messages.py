"""Saved user messages: the ID each one keeps in its transcript heading, and which ones need no record.

Since 3.9 a message gets its ID when it is first saved, and the ID is written in its heading, so writing the
transcript again, after a change of redaction rules or from the host's own copy of the turn, keeps it. The ID covers
the transcript and the message number besides the text, so the same sentence in two sessions is reconciled in each.
A message saved by 3.8 or older has no ID in its heading; its ID is the hash of its text alone, as before, so the
reconcile rows written for it stay valid. The two kinds tell apart by length: 10 hex digits before 3.9, 12 since.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from datetime import datetime, timezone

from .core import sha
from .schema import HEADING_NOTE

ENTRY_RE = re.compile(r'^## (\d+)\. (user|assistant)(' + HEADING_NOTE + r')\n\n(.*?)(?=^## \d+\. (?:user|assistant)'
                      + HEADING_NOTE + r'\n|\Z)', re.M | re.S)
ID_RE = re.compile(r' \[(m[0-9a-f]{10}(?:[0-9a-f]{2})?)\]$')
STAMP_RE = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ')
# Messages that carry no requirement: continuation prompts, acknowledgements, thanks. Yes, no, 是, 对, 可以 and 行
# can answer a question, so since 3.9 they are reconciled like other messages; messages saved before keep the old rule.
ROUTINE = re.compile(r'^(?:(?:继续|继续吧|接着|好的?|好|ok(?:ay)?|嗯|谢谢|thanks?|continue|go on|next|'
                     r'完美丝滑接续任务|完美接续中断任务|继续中断任务|继续未完成任务)[。.!！,，\s]*)+$', re.I)
ROUTINE_BEFORE_39 = re.compile(r'^(?:(?:继续|继续吧|接着|好的?|好|行|可以|ok(?:ay)?|yes|no|是的?|对|嗯|谢谢|thanks?|continue|'
                               r'go on|next|完美丝滑接续任务|完美接续中断任务|继续中断任务|继续未完成任务)[。.!！,，\s]*)+$', re.I)
ROUTINE_MAX = 40
ATTACHMENT = re.compile(r'(?:\s*\[Image #\d+\])+\s*$')


def normal(text: str) -> str:
    return ' '.join(text.split())


def old_id(body: str) -> str:
    return 'm' + sha(normal(body).encode('utf-8'))[:10]


def new_id(rel: str, number: int, body: str) -> str:
    return 'm' + sha(f'{rel}\n{number}\n{normal(body)}'.encode('utf-8'))[:12]


def routine(mid: str, body: str) -> bool:
    rule = ROUTINE_BEFORE_39 if len(mid) == 11 else ROUTINE
    return len(body) <= ROUTINE_MAX and bool(rule.match(body))


def after(messages: list, since: float | None):
    """The messages of one session sent at or after since, given as (role, text, note) with the host's time in the
    note. A message with no time of its own goes with the timed message before it. None when the host stored no time
    for any message: nothing then tells which ones came before, and the file's own date does not either, because a
    session that began earlier is still being written."""
    if since is None:
        return messages
    kept, passed, timed = [], False, False
    for message in messages:
        stamp = STAMP_RE.search(message[2] if len(message) > 2 else '')
        if stamp:
            timed = True
            sent = datetime.strptime(stamp.group(0), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp()
            passed = sent >= since
        if passed:
            kept.append(message)
    return kept if timed or not messages else None


def entries(text: str) -> list:
    """(number, role, stamp, ID, body). Older assistant headings have no ID."""
    found = []
    for match in ENTRY_RE.finditer(text):
        note, body = match.group(3), match.group(4).strip()
        stored, stamp = ID_RE.search(note), STAMP_RE.search(note)
        mid = stored.group(1) if stored else old_id(body) if match.group(2) == 'user' and body else None
        found.append((int(match.group(1)), match.group(2), stamp.group(0) if stamp else '', mid, body))
    return found


def carry(prior: list, rel: str, users: list, role='user') -> list:
    """Match visible text in sequence. A timestamp alone cannot make an edited instruction the same message."""
    old, positions, previous_at, native = [], {}, {}, {}
    for number, turn in enumerate(prior, 1):
        if turn.role == role:
            key = ATTACHMENT.sub('', turn.body).strip()
            if turn.source_id:
                native[turn.source_id, key] = len(old)
            else:
                positions.setdefault(key, []).append(len(old))
            previous_at[number] = turn.mid
            old.append(turn.mid)
    ids, start, reserved = [], 0, set(old)
    namespace = rel if role == 'user' else rel + '#assistant'
    for number, body, source_id in users:
        key = ATTACHMENT.sub('', body).strip()
        exact = native.get((source_id, key))
        if exact is not None:
            ids.append(old[exact])
            continue
        candidates = positions.get(key, [])
        place = bisect_left(candidates, start)
        if place == len(candidates):
            mid = new_id(namespace + source_id + previous_at.get(number, ''), number, body)
            while mid in reserved:
                mid = new_id(namespace + mid, number, body)
            reserved.add(mid)
            ids.append(mid)
        else:
            hit = candidates[place]
            ids.append(old[hit])
            start = hit + 1
    return ids
