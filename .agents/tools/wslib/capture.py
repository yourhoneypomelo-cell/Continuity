"""Copy host transcripts into docs/chats/ from hook events. Never raises into the host."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import tables
from .core import atomic_write, read, safe_path, today
from .hostmessages import INJECTED_PREFIXES, _message, _snapshot, extract  # extract is also a public parser entry point
from .locks import lock
from .coverage import redact, redact_pasted
from .messages import after, new_id, routine
from .transcripts import Turn, escape_headings, incoming, markdown, rewrite, saved, source_edit, visible_copy
from .schema import CHAT_INDEX

INDEX_HEADERS = ('Date', 'Host', 'Session', 'Messages', 'Transcript', 'Raw copy')
TRANSCRIPT_KEYS = ('transcript_path', 'transcriptPath', 'transcript', 'transcriptFile')
SESSION_KEYS = ('session_id', 'sessionId', 'conversation_id', 'conversationId', 'chat_id')
MAX_RAW = 50 * 1024 * 1024


def _first(data: dict, keys) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def render(host: str, session: str, messages: list, source: str, old: str = '', rel: str = '') -> str:
    rel = rel or f'docs/chats/{host}/{session}.md'
    return markdown(host, session, incoming(saved(old, rel), rel, messages), source)


def _real(path: str) -> str:
    """The path with symlinks resolved, so /var and /private/var compare equal on macOS."""
    return os.path.normcase(os.path.realpath(path))


def _same_dir(a: str, b: Path) -> bool:
    """An empty or relative folder would resolve against the current directory and match any project."""
    if not isinstance(a, str) or not os.path.isabs(a):
        return False
    try:
        return _real(a) == _real(str(b))
    except (OSError, ValueError):
        return False


IMPORT_HOSTS = ('kimi', 'codex', 'antigravity', 'kiro', 'cursor', 'workbuddy', 'codebuddy', 'qoder', 'qwen', 'gemini', 'dsh')
# Stores that name the project folder in an index or a first line, so a scan takes about a second.
# Cursor and Antigravity stores must be read in full; import them by hand with "ws chats import".
AUTO_IMPORT = ('kimi', 'codex', 'kiro', 'workbuddy', 'codebuddy', 'qoder', 'qwen', 'gemini', 'dsh')
# Stores laid out as <home>/projects/<folder>/... whose lines carry the session's "cwd".
CWD_STORES = {
    'workbuddy': [('WORKBUDDY_HOME', '.workbuddy-ai'), (None, '.workbuddy')],
    'codebuddy': [('CODEBUDDY_CONFIG_DIR', '.codebuddy')],
    'qoder': [('QODER_HOME', '.qoder'), ('QODER_CONFIG_DIR', '.qoder')],
    'qwen': [('QWEN_HOME', '.qwen')],
}
CWD_PATTERNS = ('projects/*/*.jsonl', 'projects/*/transcript/*.jsonl', 'projects/*/chats/*.jsonl')
CWD_RE = re.compile(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _json_string(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except ValueError:
        return ''


SCAN_CACHE = '.agents/cache/session-scan.json'
# Part of each cached scan result's key: results found under older matching rules are scanned again.
SCAN_RULES = 2


def _markers(root: Path) -> list:
    """Byte forms of the project path as it appears in host transcripts: plain, JSON-escaped and with slashes, and
    on Windows with the drive letter in either case."""
    text = str(root.resolve())
    forms = {text, text.replace('\\', '/')}
    if re.match(r'[A-Za-z]:', text):
        forms |= {f[0].swapcase() + f[1:] for f in forms}
    return sorted({f.encode('utf-8') for f in forms} | {json.dumps(f)[1:-1].encode('utf-8') for f in forms}
                  | {json.dumps(f, ensure_ascii=False)[1:-1].encode('utf-8') for f in forms})


def _mentions(root: Path, paths: list) -> list:
    """Paths whose text names this project. Results are cached by size and modification time, because a
    host store can hold gigabytes of transcripts that would otherwise be read at every session start."""
    markers = _markers(root)
    # A mention ends where the path does: "E:/a/T8" does not mention E:/a/T80.
    mention = re.compile(b'(?:' + b'|'.join(re.escape(m) for m in markers) + rb')(?=[\\/"\'\s])')
    cache_path = root / SCAN_CACHE
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        cache = cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        cache = {}
    fresh, found = {}, []
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            continue
        key = f'{SCAN_RULES}:{info.st_size}:{info.st_mtime_ns}'
        hit = cache.get(str(path))
        if isinstance(hit, list) and len(hit) == 2 and hit[0] == key and isinstance(hit[1], bool):
            match = hit[1]
        else:
            match = False
            try:
                with path.open('rb') as stream:
                    tail = b''
                    for chunk in iter(lambda: stream.read(1 << 20), b''):
                        if mention.search(tail + chunk):
                            match = True
                            break
                        tail = (tail + chunk)[-512:]
                    else:
                        match = any(tail.endswith(m) for m in markers)
            except OSError:
                continue
        fresh[str(path)] = [key, match]
        if match:
            found.append(path)
    if fresh != cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(cache_path, json.dumps(fresh))
        except OSError:
            pass
    return found


CWD_CACHE = '.agents/cache/session-cwd.json'


def _session_folders(root: Path, paths: list, first_line: bool) -> dict:
    """path -> the working folder a session file records. A session never moves to another folder, so a
    found answer is cached by path and only new files are read."""
    cache_path = root / CWD_CACHE
    try:
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        cache = cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        cache = {}
    result, changed = {}, False
    for path in paths:
        key = str(path)
        if isinstance(cache.get(key), str) and cache[key]:
            result[key] = cache[key]
            continue
        try:
            with path.open('rb') as stream:
                head = stream.read(65536).decode('utf-8', errors='replace')
                if not first_line and not CWD_RE.search(head):
                    head += stream.read(1 << 20).decode('utf-8', errors='replace')
        except OSError:
            continue
        match = CWD_RE.search(head.split('\n', 1)[0] if first_line else head)
        folder = _json_string(match[1]) if match else ''
        if folder:
            cache[key] = folder
            changed = True
        result[key] = folder
    if changed:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(cache_path, json.dumps(cache))
        except OSError:
            pass
    return result


THREAD_SOURCE_RE = re.compile(r'"thread_source"\s*:\s*"([^"]*)"')
SUBAGENT_RE = re.compile(r'"source"\s*:\s*\{\s*"subagent"')


def _codex_delegated(path: Path) -> bool:
    """A Codex subagent or guardian rollout: its user turns are prompts the agent wrote, not the user."""
    try:
        with path.open('rb') as stream:
            head = stream.readline(65536).decode('utf-8', errors='replace')
    except OSError:
        return False
    found = THREAD_SOURCE_RE.search(head)  # newer CLIs: "user", "subagent" or "guardian_review"
    return found[1] != 'user' if found else bool(SUBAGENT_RE.search(head))


def local_sessions(root: Path, host: str) -> list:
    """Find (session_id, transcript_path) pairs a host stored for this project folder."""
    found = []
    home = Path.home()
    if host in CWD_STORES:
        seen = set()
        for variable, default in CWD_STORES[host]:
            base = Path(os.environ[variable]) if variable and os.environ.get(variable) else home / default
            paths = [p for pattern in CWD_PATTERNS for p in (base.glob(pattern) if base.is_dir() else []) if p not in seen]
            seen.update(paths)
            folders = _session_folders(root, paths, first_line=False)
            found += [(p.stem, p) for p in paths if _same_dir(folders.get(str(p), ''), root)]
        found.sort(key=lambda item: item[1].stat().st_mtime)
        return found[-50:]
    if host == 'gemini':
        # Gemini CLI: ~/.gemini/projects.json maps each project folder to a slug under tmp/.
        base = Path(os.environ.get('GEMINI_HOME') or home / '.gemini')
        try:
            projects = json.loads((base / 'projects.json').read_text(encoding='utf-8')).get('projects') or {}
        except (OSError, ValueError, AttributeError):
            projects = {}
        projects = projects if isinstance(projects, dict) else {}
        slugs = [slug for folder, slug in projects.items()
                 if isinstance(slug, str) and re.fullmatch(r'[A-Za-z0-9._-]+', slug) and slug not in ('.', '..')
                 and _same_dir(folder, root)]
        for slug in slugs:
            for path in (base / 'tmp' / slug / 'chats').glob('*.jsonl'):
                found.append((path.stem, path))
        found.sort(key=lambda item: item[1].stat().st_mtime)
        return found[-50:]
    if host == 'kiro':
        # Kiro IDE: sessions/<workspace hash>/<session>/session.json names the workspace folders.
        base = Path(os.environ.get('KIRO_HOME') or home / '.kiro') / 'sessions'
        for meta in base.glob('*/sess_*/session.json') if base.is_dir() else []:
            try:
                data = json.loads(meta.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            folders = (data.get('workspacePaths') or []) + (data.get('rootPaths') or [])
            log = meta.with_name('messages.jsonl')
            if log.is_file() and any(isinstance(f, str) and _same_dir(f, root) for f in folders):
                found.append((meta.parent.name, log))
        found.sort(key=lambda item: item[1].stat().st_mtime)
    elif host == 'cursor':
        # Cursor keeps agent transcripts per project folder, but the folder name does not say which project.
        # A transcript belongs here when it mentions this project's path.
        base = home / '.cursor' / 'projects'
        paths = list(base.glob('*/agent-transcripts/*/*.jsonl')) if base.is_dir() else []
        found = [(p.stem, p) for p in _mentions(root, paths)]
        found.sort(key=lambda item: item[1].stat().st_mtime)
    elif host == 'kimi':
        base = Path(os.environ.get('KIMI_CODE_HOME') or home / '.kimi-code')
        index = base / 'session_index.jsonl'
        if index.is_file():
            for line in index.read_text(encoding='utf-8', errors='replace').splitlines():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                wire = Path(item.get('sessionDir', '')) / 'agents' / 'main' / 'wire.jsonl'
                if _same_dir(item.get('workDir', ''), root) and wire.is_file():
                    found.append((item['sessionId'], wire))
    elif host == 'codex':
        base = Path(os.environ.get('CODEX_HOME') or home / '.codex') / 'sessions'
        paths = sorted(base.rglob('rollout-*.jsonl')) if base.is_dir() else []
        # The first line is the session meta; it names the working folder.
        folders = _session_folders(root, paths, first_line=True)
        found = [(p.stem, p) for p in paths if _same_dir(folders.get(str(p), ''), root) and not _codex_delegated(p)]
    elif host == 'antigravity':
        # The transcript has no working directory, so match conversations that touched this project's files.
        paths = []
        for app in ('antigravity-cli', 'antigravity', 'antigravity-ide', 'antigravity-id'):
            brain = home / '.gemini' / app / 'brain'
            paths += list(brain.glob('*/.system_generated/logs/transcript.jsonl')) if brain.is_dir() else []
        found = [(p.parents[2].name, p) for p in _mentions(root, paths)]
        found.sort(key=lambda item: item[1].stat().st_mtime)
    else:
        raise ValueError(f'import supports {", ".join(IMPORT_HOSTS)}; use hooks for {host}')
    return found[-50:]


def import_sessions(root: Path, host: str, since: float | None = None) -> dict:
    """Copy this project's sessions of one host. With since, only messages sent at or after that time are copied,
    each judged by its own time. "untimed" counts the sessions left out because the host stored no message time."""
    if host == 'dsh':
        from . import dsh
        return dsh.import_sessions(root, since=since)
    # A file last written before since holds no later message, so it is not opened at all.
    results = [capture(root, host, 'import', {'session_id': sid, 'transcript_path': str(path)}, since)
               for sid, path in local_sessions(root, host) if since is None or path.stat().st_mtime >= since]
    kept = [r for r in results if r.get('captured')]
    return {'host': host, 'sessions': len(kept), 'messages': sum(r.get('messages', 0) for r in kept),
            'untimed': sum(1 for r in results if r.get('untimed'))}


UNTIMED = ('{count} {host} sessions store no time for their messages, so nothing tells which ones are from before '
           'the workspace was set up; they were left out. "ws chats import {host} --all" copies them whole, when the '
           'user asks for that.')


IMPORT_QUESTION = ("Ask the user once, in your reply: may ws start copy this project's chats from the AI tools on this "
                   'machine (Codex, Kiro, Kimi Code, Gemini, Qwen Code, Qoder, CodeBuddy, WorkBuddy and DeepSeek '
                   'Harness) into docs/chats/, leaving out chats from before the workspace was set up? Then set '
                   'WORKSPACE "chat_import" in docs/state/ARCHITECTURE.md to "on" or "off".')


def import_rule(root: Path) -> tuple:
    """("on", "off" or "ask", and the time messages must be newer than, or None). WS_IMPORT=0 or 1 in the environment
    wins over WORKSPACE "chat_import", so a user decides for every project at once (owner decision D1)."""
    from .core import WorkspaceError, config
    try:
        settings = config(root)
    except (WorkspaceError, ValueError, OSError):
        settings = {}
    rule = {'0': 'off', '1': 'on'}.get(os.environ.get('WS_IMPORT', ''), settings.get('chat_import', 'ask'))
    since = settings.get('chat_import_since')
    if since:
        moment = datetime.fromisoformat(str(since))
        since = (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()
    return rule, since or None


def import_all(root: Path, since: float | None = None, untimed: dict | None = None) -> dict:
    """Copy this project's sessions from every host store found on this machine. Never raises. When a dict is passed
    as untimed, it receives per host the sessions left out for lack of message times."""
    found = {}
    for host in AUTO_IMPORT:
        try:
            if host == 'dsh':
                from . import dsh
                result = dsh.import_sessions(root, automatic=True, since=since)
            else:
                result = import_sessions(root, host, since)
        except Exception:  # an unreadable store of one host must not stop the others
            continue
        if result['sessions']:
            found[host] = result['sessions']
        if untimed is not None and result.get('untimed'):
            untimed[host] = result['untimed']
    return found


def session_name(payload: dict) -> str:
    raw = _first(payload, SESSION_KEYS) or 'unknown'
    name = re.sub(r'[^A-Za-z0-9_-]', '-', raw)[:64].strip('-') or 'unknown'
    # Different IDs that clean to the same name, such as a/b and a-b, keep separate files.
    return name if name == raw else f'{name[:52]}-{hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]}'


def journal(root: Path, host: str, payload: dict, role: str, text: str) -> dict:
    """Append one message to docs/chats/<host>/<session>.md for hosts whose hooks send the text, not a file."""
    text = text.strip() if isinstance(text, str) else ''
    if not text or text.startswith(INJECTED_PREFIXES):
        return {'captured': False, 'reason': 'no message text in the hook payload'}
    host = re.sub(r'[^a-z0-9-]', '-', host.lower())[:24] or 'host'
    session = session_name(payload)
    rel = f'docs/chats/{host}/{session}.md'
    with lock(root):
        return _append(root, host, session, rel, role, text)


def submit(root: Path, host: str, payload: dict) -> dict:
    """Prompt-submit hook: save the user message as it arrives, so the turn can reconcile it before its checkpoint.
    The text is cleaned as the host's own copy will be, and the Stop hook's rewrite keeps the ID it gets here."""
    prompt = _first(payload, PROMPT_KEYS)
    found = _message({'role': 'user', 'content': prompt}) if prompt else None
    if not found:
        return {'captured': False, 'reason': 'no typed text in the hook payload'}
    source = _first(payload, TRANSCRIPT_KEYS)
    if host == 'codex' and source and Path(source).is_file() and _codex_delegated(Path(source)):
        return {'captured': False, 'reason': 'a subagent or guardian thread; its prompts come from the agent'}
    return journal(root, host, payload, 'user', found[1])


def _append(root: Path, host: str, session: str, rel: str, role: str, text: str) -> dict:
    path = safe_path(root, rel)
    existing = path.read_text(encoding='utf-8') if path.is_file() else ''
    turns = saved(existing, rel)
    body = (redact_pasted(text) if role == 'user' else redact(text)).strip()
    if turns and (turns[-1].role, turns[-1].body) == (role, escape_headings(body)):
        _index(root, host, session, len(turns), rel, None)
        return {'captured': False, 'reason': 'same message already written'}
    number = len(turns) + 1
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    mid = new_id(rel if role == 'user' else rel + '#assistant', number, escape_headings(body))
    turns.append(Turn(role, body, stamp, mid, True))
    history = safe_path(root, f'docs/chats/{host}/raw/revisions/{session}').is_dir()
    atomic_write(path, markdown(host, session, turns, 'host hook', history=history, edit=source_edit(existing)))
    _index(root, host, session, number, rel, None)
    found = {'captured': True, 'messages': number, 'transcript': rel}
    return {**found, 'id': mid} if role == 'user' and not routine(mid, body) else found


def _index(root: Path, host: str, session: str, count: int, transcript_rel: str, raw_rel: str | None):
    """Add or update the INDEX.md row of a session. A raw_rel of None keeps the raw copy the row names."""
    index = read(root, CHAT_INDEX)
    row = {'Date': today(), 'Host': host, 'Session': session, 'Messages': str(count),
           'Transcript': transcript_rel, 'Raw copy': raw_rel or 'none'}
    existing = [r for r in tables.parse(index, INDEX_HEADERS, CHAT_INDEX) if r['Session'] == session and r['Host'] == host]
    if raw_rel is None and existing:
        row['Raw copy'] = existing[0].get('Raw copy') or 'none'
    if existing:
        if all(existing[0].get(key) == row[key] for key in INDEX_HEADERS if key != 'Date'):
            return
        start, actual, raw = tables._find(index, INDEX_HEADERS, CHAT_INDEX)
        lines = index.split('\n')
        for i, cells in raw:
            if cells[1:3] == [host, session]:
                lines[i] = tables.render_row(actual, row)
        index = '\n'.join(lines)
    else:
        index = tables.append(index, INDEX_HEADERS, CHAT_INDEX, row)
    atomic_write(safe_path(root, CHAT_INDEX), index)


PROMPT_KEYS = ('prompt', 'user_prompt', 'userPrompt')
REPLY_KEYS = ('last_assistant_message', 'lastAssistantMessage', 'text', 'response')


def capture(root: Path, host: str, event: str, payload: dict, since: float | None = None) -> dict:
    """Copy one session into docs/chats/. With since, an import keeps only the messages sent at or after it."""
    source = _first(payload, TRANSCRIPT_KEYS) or (os.environ.get('CURSOR_TRANSCRIPT_PATH') if host == 'cursor' else None)
    if not source:
        # Kiro and Cursor send the prompt and the reply in the hook payload instead of a transcript file.
        prompt, reply = _first(payload, PROMPT_KEYS), _first(payload, REPLY_KEYS)
        if prompt or reply:
            return journal(root, host, payload, 'user' if prompt else 'assistant', prompt or reply)
        return {'captured': False, 'reason': 'the hook payload has no transcript path and no message text'}
    host = re.sub(r'[^a-z0-9-]', '-', host.lower())[:24] or 'host'
    session = session_name(payload)
    path = Path(source).expanduser()
    if not path.is_file():
        return {'captured': False, 'reason': f'transcript not found: {source}'}
    if host == 'codex' and _codex_delegated(path):
        return {'captured': False, 'reason': 'a subagent or guardian thread; its prompts come from the agent'}
    folder = f'docs/chats/{host}'
    whole, edit = _snapshot(path)
    messages = whole
    if since is not None:
        messages = after(whole, since)
        if messages is None:
            return {'captured': False, 'untimed': True, 'reason': 'the host stored no time for any message'}
        if not messages:
            return {'captured': False, 'reason': 'every message is from before the workspace was set up'}
    last = payload.get('last_assistant_message') or payload.get('lastAssistantMessage')
    # Hosts flush the transcript after Stop hooks run, so the final reply may be missing from the file.
    clipped = len(messages) < len(whole)
    if isinstance(last, str) and last.strip() and (not messages or messages[-1][:2] != ('assistant', last.strip())):
        messages.append(('assistant', last.strip(), ''))
    with lock(root):
        transcript_rel = f'{folder}/{session}.md'
        turns = rewrite(root, transcript_rel, host, session, messages, path.name, since, edit)
        raw_rel = f'{folder}/raw/{session}{path.suffix or ".txt"}'
        if clipped:
            # The host's file also holds the messages that were left out, so no raw copy of it is kept.
            safe_path(root, raw_rel).unlink(missing_ok=True)
            raw_rel = 'none'
        elif path.stat().st_size <= MAX_RAW and os.environ.get('WS_CAPTURE_RAW', '1') != '0':
            atomic_write(safe_path(root, raw_rel), visible_copy(turns, path.suffix))
        else:
            raw_rel = 'none'
        _index(root, host, session, len(turns), transcript_rel if turns else 'none', raw_rel)
    return {'captured': bool(turns), 'messages': len(turns), 'transcript': transcript_rel, 'event': event}
