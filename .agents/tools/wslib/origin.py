"""Recognise host envelopes without treating ordinary user prose as an automation event."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOTICE = 'Briefly inform the user about the task result and perform any follow-up actions (if needed).'
WORKER = 'WS_ROLE=worker: you are a helper session of a main session.'
STAMP = re.compile(r'<timestamp>([^<>\n]{1,90})</timestamp>')
QUERY = re.compile(r'<user_query>\s*(.*?)\s*</user_query>', re.S)
CAPABILITIES = re.compile(r'<available_subagent_types>.*?</available_subagent_types>'
                          r'(?:\s*<available_subagent_models>.*?</available_subagent_models>)?'
                          r'(?:\s*<dynamic_tool_catalog>.*?</dynamic_tool_catalog>)?', re.S)
WRAPPERS = re.compile(r'<(user_info|image_files|attached_files|open_and_recently_viewed_files|attachments|'
                      r'files_mentioned)>.*?</\1>\s*', re.S)
IMAGE = re.compile(r'\[Image(?: #\d+)?\]\s*')
DATE = re.compile(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), '
                  r'([A-Za-z]{3}) (\d{1,2}), (\d{4}), (\d{1,2}):(\d{2}) (AM|PM) \(UTC([+-])(\d{1,2})(?::(\d{2}))?\)')
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def cursor_store(path: Path) -> bool:
    parts = [p.casefold() for p in path.parts]
    return any(parts[i:i + 2] == ['.cursor', 'projects'] and 'agent-transcripts' in parts[i + 3:-1]
               for i in range(len(parts) - 4))


def timestamp(value: str) -> str:
    match = DATE.fullmatch(value)
    try:
        if match:
            month, day, year, hour, minute, ampm, sign, zone, offset = match.groups()
            if not 1 <= int(hour) <= 12 or int(offset or 0) >= 60:
                return ''
            tz = timezone(timedelta(hours=int(zone), minutes=int(offset or 0)) * (1 if sign == '+' else -1))
            moment = datetime(int(year), MONTHS.index(month) + 1, int(day), int(hour) % 12 + 12 * (ampm == 'PM'),
                              int(minute), tzinfo=tz)
        else:
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                return ''
        return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except (ValueError, OverflowError):
        return ''


def classify(text: str, cursor=False, *, legacy=False) -> tuple:
    """Return origin, visible text, UTC time. Only typed envelopes and specific signatures are routed."""
    body = text.strip()
    tail, when, images = body, '', 0
    while tail:
        stamp = STAMP.match(tail)
        image = IMAGE.match(tail)
        boundary = stamp or image or WRAPPERS.match(tail)
        if not boundary:
            break
        if stamp:
            when = timestamp(stamp[1]) or when
        if image:
            images += 1
        tail = tail[boundary.end():].strip()
    if when and not tail and not images:
        return 'timestamp', '', when
    query = QUERY.fullmatch(tail)
    if query:
        body = query[1].strip()
    if body.startswith(WORKER):
        return 'worker-assignment', '', when
    if ((query and when) or (cursor and legacy)) and body == NOTICE:
        return 'host-notice', '', when
    if (cursor or when or (legacy and '<dynamic_tool_catalog>' in tail)) and CAPABILITIES.fullmatch(tail):
        return 'host-capabilities', '', when
    if images and (query or not tail):
        marks = ' '.join(f'[Image #{i + 1}]' for i in range(images))
        body = (body + '\n\n' + marks).strip() if query else marks
    return 'human', body, when
