"""Read the visible conversation from host transcript formats."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path

from . import origin
from .redaction import redact_pasted


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get('type') in (None, 'text', 'input_text', 'output_text') \
                    and not item.get('thought'):  # Qwen and Gemini mark hidden reasoning parts
                parts.append(_text(item.get('text') or item.get('content') or ''))
        # Claude Code puts a system reminder part before the typed text; drop injected parts, keep the rest.
        typed = [p for p in parts if p and not p.lstrip().startswith(INJECTED_PREFIXES)]
        return '\n'.join(typed if typed else [p for p in parts if p])
    if isinstance(content, dict):
        if content.get('thought') or content.get('type') not in (None, 'text', 'input_text', 'output_text'):
            return ''
        return _text(content.get('text') or content.get('content') or content.get('parts') or '')
    return ''


def _role(record: dict) -> str | None:
    for candidate in (record, record.get('message') if isinstance(record.get('message'), dict) else None,
                      record.get('payload') if isinstance(record.get('payload'), dict) else None):
        if not candidate:
            continue
        role = candidate.get('role') or candidate.get('type') or candidate.get('author')
        if isinstance(role, dict):
            role = role.get('role')
        if role in ('user', 'human'):
            return 'user'
        if role in ('assistant', 'model', 'ai', 'gemini'):
            return 'assistant'
    return None


# Text the host injects as a user turn: instructions, environment, reminders.
INJECTED_PREFIXES = ('<system-reminder>', '<system-reminder ', '<command-', '# AGENTS.md instructions', '<environment_context>',
                     '<user_instructions>', '<INSTRUCTIONS>', '<skills_instructions>', '<turn_aborted>',
                     '<user_info>', '<rules>', '<recent_agents_context>',
                     'The last user message was not recorded and no reason was given.',
                     '[Request interrupted by user', '<local-command-', '<heartbeat>', '<subagent_notification>',
                     '<external_codex_apps_', '<recommended_plugins>', '<codex_delegation>', '<codex_internal_context',
                     '<send_user_message_question_reply>')
# Codex IDE extension: open files and selections come first, the typed text follows the last heading.
CODEX_IDE_REQUEST = re.compile(r'^## My request(?: for Codex)?:[ \t]*$', re.M)
CODEX_IDE_START = ('# Context from my IDE setup', '# Files pasted by the user', '# Files mentioned by the user')
CODEX_IMAGE = re.compile(r'(?:\n[ \t]*)+<image name=\[Image #(\d+)\] path="[^"\n]+">[ \t\r\n]*</image>[ \t]*')
# Claude Code origin kinds whose text the host wrote: background task results, cloud-agent continuations.
HOST_ORIGINS = ('task-notification', 'auto-continuation')


def _answers(record: dict):
    """A user's choice in a host question tool, which hosts store as tool output, not as a user turn."""
    result = record.get('toolUseResult')
    if isinstance(result, dict) and isinstance(result.get('answers'), dict) and result['answers']:
        # Claude Code AskUserQuestion
        lines = [f'{q}: {a}' for q, a in result['answers'].items() if isinstance(a, str)]
        return ('user', 'Answered: ' + '; '.join(lines)) if lines else None
    payload = record.get('payload') if isinstance(record.get('payload'), dict) else None
    if payload and payload.get('type') == 'interaction_resolved' and isinstance(payload.get('selectedOption'), str):
        # Kiro question tool; tool approvals carry an outcome but no selected option
        return ('user', 'Answered: ' + payload['selectedOption'])
    return None


def _message(record: dict, cursor=False, metadata=None):
    """Return (role, text) for a visible message, or None for tool traffic and metadata."""
    answered = _answers(record)
    if answered:
        return answered
    provider = record.get('providerData') if isinstance(record.get('providerData'), dict) else {}
    if record.get('isMeta') or provider.get('isMeta'):
        return None  # CodeBuddy and WorkBuddy mark host-inserted turns
    if record.get('isCompactSummary') or record.get('type') == 'api-request-blob':
        return None  # Claude Code compaction summary and API request dumps, written as user turns
    if isinstance(record.get('origin'), dict) and record['origin'].get('kind') in HOST_ORIGINS:
        return None  # Claude Code: typed text has kind "human"; unknown kinds are kept
    if provider.get('skipRun') or provider.get('error'):
        return None  # WorkBuddy error stubs such as "502" or "aborted"
    if record.get('provenance') not in (None, 'real_user', 'assistant_output'):
        return None  # Qwen Code marks system-inserted turns
    if record.get('type') == 'response_item' and (record.get('payload') or {}).get('type') != 'message':
        return None
    if record.get('type') == 'event_msg':
        return None
    if isinstance(record.get('payload'), dict) and 'id' in record and 'timestamp' in record and \
            record['payload'].get('type') in ('user', 'assistant', 'tool_call', 'tool_result', 'agent_note',
                                              'turn_start', 'turn_end', 'usage_summary', 'session_metadata',
                                              'session_event', 'steering_inclusion', 'pending_interaction',
                                              'interaction_resolved', 'sub_agent_start', 'sub_agent_complete',
                                              'session_start', 'tombstone'):
        # Kiro session log: user text, and assistant text spoken to the user ("Say")
        inner = record['payload']
        if inner.get('type') == 'user' and isinstance(inner.get('content'), str) and inner['content'].strip():
            return 'user', inner['content'].strip()
        if inner.get('type') == 'assistant' and inner.get('operationType') == 'Say' and isinstance(inner.get('content'), str):
            text = inner['content'].strip()
            return ('assistant', text) if text else None
        return None
    if record.get('type') == 'user' and record.get('synthetic_reason'):
        return None  # Grok inserts reminders and project instructions as user turns
    if record.get('type') == 'USER_INPUT' and record.get('source') == 'USER_EXPLICIT':
        # Antigravity wraps the typed request in USER_REQUEST tags and appends metadata.
        found = re.search(r'<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>', str(record.get('content', '')), re.S)
        text = (found[1] if found else str(record.get('content', ''))).strip()
        return ('user', text) if text else None
    if record.get('type') == 'PLANNER_RESPONSE':
        text = str(record.get('content') or record.get('response') or '').strip()
        return ('assistant', text) if text else None
    if record.get('type') in ('GENERIC', 'SYSTEM_MESSAGE', 'USER_INPUT'):
        return None
    if record.get('type') == 'agent.message.appended':
        # Kimi Code wire log: a user turn has origin "user"; assistant turns carry text parts.
        inner = (record.get('message') or {}).get('message') or {}
        if inner.get('role') == 'user' and ((record['message'].get('meta') or {}).get('origin') or {}).get('kind') != 'user':
            return None
        record = {'message': inner}
    elif record.get('type', '').startswith(('context.', 'turn.', 'llm.', 'profile.', 'plugin.')):
        return None
    role = _role(record)
    if not role:
        return None
    body = record.get('message') if isinstance(record.get('message'), dict) else record.get('payload') if isinstance(record.get('payload'), dict) else record
    if (body.get('channel') in ('analysis', 'hidden') or body.get('recipient') not in (None, 'all')
            or body.get('thought') or record.get('channel') in ('analysis', 'hidden')):
        return None
    if role == 'user':
        content = body.get('content')
        parts = content if isinstance(content, list) else [content]
        for part in parts:
            value = part.get('text') if isinstance(part, dict) and part.get('type') in ('input_text', 'text') else part
            if isinstance(value, str) and value.strip().startswith('<send_user_message_question_reply>'):
                return question_reply(value)
    text = _text(body.get('content') if 'content' in body else body.get('text') or body.get('parts'))
    text = text.strip()
    if role == 'user':
        kind, text, when = origin.classify(text, cursor)
        if metadata is not None:
            metadata.update(kind=kind, when=when)
        if kind != 'human':
            return None
    if role == 'user' and text.startswith(CODEX_IDE_START):
        # An attachment-only message has nothing after the heading; keep it whole rather than lose it.
        headings = list(CODEX_IDE_REQUEST.finditer(text))
        text = text[headings[-1].end():].strip() or text if headings else text
        if headings:
            visible = CODEX_IMAGE.sub('', '\n' + text).strip()
            text = visible or ' '.join(f'[Image #{n}]' for n in CODEX_IMAGE.findall('\n' + text)) or text
    if not text or text.startswith(INJECTED_PREFIXES):
        return None
    return role, text


def question_reply(text: str):
    """Only the visible question and answer from Codex's structured user response."""
    tag = 'send_user_message_question_reply'
    match = re.fullmatch(rf'<{tag}>\s*(.*?)\s*</{tag}>', text.strip(), re.S)
    if not match:
        return None
    try:
        items = json.loads(match[1])
    except ValueError:
        return None
    if not isinstance(items, list):
        return None
    pairs = [item['question'] + '\n' + item['answer'] for item in items if isinstance(item, dict)
             and isinstance(item.get('question'), str) and isinstance(item.get('answer'), str) and item['answer'].strip()]
    return ('user', '\n\n'.join(pairs)) if pairs else None


def _replay_gemini(records: list) -> list:
    """Gemini CLI chat logs are a change log: `$set.messages` holds earlier turns, a repeated id replaces
    a message, `$rewindTo` drops a message and everything after it, `$patch` removes or reorders ids."""
    order, by_id = [], {}

    def put(message):
        if not isinstance(message, dict) or 'type' not in message:
            return
        key = message.get('id') if isinstance(message.get('id'), str) and message.get('id') else f'_{len(order)}'
        if key not in by_id:
            order.append(key)
        by_id[key] = message

    for record in records:
        if isinstance(record.get('$set'), dict):
            for message in record['$set'].get('messages') or []:
                put(message)
        elif '$rewindTo' in record:
            target = record['$rewindTo']
            if isinstance(target, str) and target in by_id:
                cut = order.index(target)
                for key in order[cut:]:
                    by_id.pop(key, None)
                del order[cut:]
        elif isinstance(record.get('$patch'), dict):
            patch = record['$patch']
            def ids(name):
                value = patch.get(name)
                return [k for k in value if isinstance(k, str)] if isinstance(value, list) else []
            for key in ids('removeIds'):
                if key in by_id:
                    by_id.pop(key)
                    order.remove(key)
            for update in patch.get('updates') if isinstance(patch.get('updates'), list) else []:
                if isinstance(update, dict) and isinstance(update.get('id'), str) and update['id'] in by_id:
                    by_id[update['id']] = {**by_id[update['id']], **update}
            wanted = list(dict.fromkeys(k for k in ids('orderIds') if k in by_id))
            if wanted:
                order = wanted + [k for k in order if k not in wanted]
        else:
            put(record)
    return [by_id[key] for key in order]


COMPACTED = '(after compaction)'


def _time(record: dict) -> str:
    """The record's UTC time as 2026-10-31T14:02:05Z, or '' when the host stores none."""
    value = record.get('timestamp') or record.get('created_at') or record.get('createdAt')
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            moment = datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc)
        elif isinstance(value, str) and value.strip():
            moment = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
            moment = moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
        else:
            return ''
    except (ValueError, OverflowError, OSError):
        return ''
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def extract(path: Path, timed: bool = False) -> list:
    """(role, text) for each visible message. With timed, (role, text, note): the note holds the time and a
    compaction mark and is written in the heading, never in the text, so message IDs stay the same."""
    turns, _ = _snapshot(path)
    return [t[:3] if timed else t[:2] for t in turns]


def _snapshot(path: Path, events=None, cursor=False) -> tuple:
    """Visible turns with their source message IDs, plus the last explicit host edit in this snapshot."""
    raw = path.read_text(encoding='utf-8', errors='replace')
    records = []
    stripped = raw.lstrip()
    if stripped.startswith('[') or (stripped.startswith('{') and '\n{' not in stripped[:2000]):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data.get('messages') or data.get('history') or data.get('items') or []
            records = [r for r in data if isinstance(r, dict)]
        except ValueError:
            records = []
    if not records:
        for line in raw.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return _visible_snapshot(records, events, cursor or origin.cursor_store(path))


def _codex_ui_message(record: dict):
    payload = record.get('payload')
    if record.get('type') != 'event_msg' or not isinstance(payload, dict) or payload.get('type') != 'item_completed':
        return None
    item = payload.get('item')
    if not isinstance(item, dict) or item.get('type') not in ('UserMessage', 'AgentMessage'):
        return None
    if item.get('phase') not in (None, 'commentary', 'final_answer', 'final'):
        return None
    role = 'user' if item['type'] == 'UserMessage' else 'assistant'
    parts = [{'type': 'text', 'text': p['text']} for p in item.get('content') or []
             if isinstance(p, dict) and p.get('type') in ('text', 'Text') and isinstance(p.get('text'), str)]
    found = _message({'role': role, 'content': parts})
    if found:
        return found, item.get('id'), _time({'timestamp': payload.get('completed_at_ms')}) or _time(record)
    return None


def _visible_snapshot(records: list, events=None, cursor=False) -> tuple:
    edit = ''
    for record in records:
        change = record.get('$patch')
        if ('$rewindTo' in record or (isinstance(change, dict) and change.get('removeIds'))
                or record.get('type') == 'resend-fork-notice'):
            edit = hashlib.sha256(json.dumps(record, sort_keys=True).encode('utf-8')).hexdigest()
    if any('$set' in r or '$rewindTo' in r or '$patch' in r for r in records):
        records = _replay_gemini(records)
    for notice in [r for r in records if r.get('type') == 'resend-fork-notice' and r.get('editedUserItemId')]:
        # WorkBuddy: an edited and resent message replaces the original and the replies it got.
        ids = [r.get('id') for r in records]
        at = next((i for i, r in enumerate(records) if r is notice), -1)
        if notice['editedUserItemId'] in ids[:max(at, 0)]:
            records = records[:ids.index(notice['editedUserItemId'])] + records[at:]
    messages, gap, seen = [], False, set()
    # One Codex turn can occur in either stream and may appear in both. Pair observations one by one.
    unmatched = defaultdict(deque)
    for record in records:
        gap = gap or bool(record.get('isCompactSummary')) or record.get('type') == 'compacted'
        ui = _codex_ui_message(record)
        if ui:
            found, identifier, stamp = ui
        else:
            meta = {}
            found = _message(record, cursor, meta)
            if events is not None and meta.get('kind', 'human') != 'human':
                kind = meta['kind']
                events[kind] = events.get(kind, 0) + 1
            identifier = record.get('uuid') or record.get('id')
            nested = record.get('message') if isinstance(record.get('message'), dict) else record.get('payload')
            if not identifier and isinstance(nested, dict):
                identifier = nested.get('id')
            stamp = (_time(record) or meta.get('when', '')) if found else ''
        if not found:
            continue
        if not (isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', identifier)
                and redact_pasted(identifier) == identifier):
            identifier = ''
        if identifier:
            key = (bool(ui), identifier, *found)
            if key in seen:
                continue
            seen.add(key)
        note = ' '.join(filter(None, (stamp, COMPACTED if gap else '')))
        if ui or record.get('type') == 'response_item':
            other = unmatched[not bool(ui), found]
            if other:
                pos = other.popleft()
                if ui:
                    previous = messages[pos]
                    if COMPACTED in previous[2] and COMPACTED not in note:
                        note = (note + ' ' + COMPACTED).strip()
                    messages[pos] = (*found, note or previous[2], identifier or previous[3])
                gap = False
                continue
            unmatched[bool(ui), found].append(len(messages))
        messages.append((*found, note, identifier))
        gap = False
    return messages, edit
