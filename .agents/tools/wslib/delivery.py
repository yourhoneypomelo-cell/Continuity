"""What a checkpoint and the brief report beside READY (3.8.0).

Delivery: the three things finished work rests on: the saved state, the acceptance behind each done task, and
whether this host was tried end to end. Shortcuts: changes that can make a task easier to pass. They are listed,
never refused, because each also has honest reasons."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import evidence, logs
from .core import safe_path

# Historical observations in HOSTS.md. A host name alone says nothing about this installation or model.
TRIALS = {'kimi': 'Kimi Code 2.4.1 completed a two-session product trial',
          'codex': 'Codex 0.166.0 loaded the contract and reached its account limit before completing a handoff',
          'antigravity': 'Antigravity CLI 1.4.12 started the second task and then reached its account limit'}


def _ids(ids: list) -> str:
    return ', '.join(ids[:8]) + (f' and {len(ids) - 8} more' if len(ids) > 8 else '')


def _runs(root: Path, ids: set) -> dict:
    """Every run recorded for these tasks, accepted or rejected, oldest first."""
    found = {rid: [] for rid in ids}
    folder = safe_path(root, 'docs/archive/checks')
    for path in folder.glob('*.json') if ids and folder.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for rid in set(data.get('for_tasks') or []) & ids:
            found[rid].append(data)
    # Two runs can start within one second; every run after the first starts at a later workspace revision.
    return {rid: sorted(runs, key=lambda d: (d.get('started_at') or '', d.get('revision') or 0)) for rid, runs in found.items()}


def shortcuts(root: Path, previous, rows: list) -> list:
    """For the tasks done since the previous seal: test files that differ between a task's first run and its
    accepted run, a run command that changed, and verify runs that used --because."""
    from .validate import _fresh
    done = {r['ID'] for r in rows if r['Status'] == 'done' and _fresh(previous, r)}
    lines = []
    for rid, runs in sorted(_runs(root, done).items(), key=lambda item: int(item[0][1:])):
        accepted = [r for r in runs if r.get('accepted')]
        if len(runs) < 2 or not accepted:
            continue
        first, last = runs[0], accepted[-1]
        before, after = first.get('source_files') or {}, last.get('source_files') or {}
        tests = sorted(f for f in set(before) | set(after) if evidence.TEST_FILE.search(f) and before.get(f) != after.get(f))
        if tests:
            lines.append(f'{rid}: test files changed between its first run and the accepted one: {", ".join(tests[:4])}')
        if first.get('command') != last.get('command'):
            lines.append(f'{rid}: the run command changed from "{" ".join(first.get("command") or [])}" to '
                         f'"{" ".join(last.get("command") or [])}"')
    since = ((previous or {}).get('created_at') or '')[:10]
    for entry in logs.live_rows(root, 'MAINTENANCE_LOG'):
        if entry.get('Event') == 'verify override' and entry.get('Date', '') >= since and \
                set(re.findall(r'\bT[1-9]\d*\b', entry.get('Detail', ''))) & done:
            lines.append('verify ran another command than the acceptance: ' + entry['Detail'])
    return lines


def host_line(root: Path) -> str:
    from .doctor import current_host
    host = current_host()
    if not host:
        return 'Host: not identified by a session variable, so whether it was tried end to end is not known here.'
    trials = sorted(p.name for p in (root / 'docs/archive/trials').glob(f'*-{host}*.md')) \
        if (root / 'docs/archive/trials').is_dir() else []
    if trials:
        return f'Host: {host}. Project trial record to inspect: docs/archive/trials/{trials[-1]}.'
    if host in TRIALS:
        return f'Host: {TRIALS[host]} (HOSTS.md). A handoff with this installation has no project trial record.'
    return (f'Host: {host} was not tried end to end; how it loads AGENTS.md and runs hooks is documented, not '
            'confirmed (HOSTS.md).')


def delivery_lines(root: Path, previous, rows: list, state_text: str, stale=None) -> list:
    """The three lines a delivery rests on, then the shortcuts worth a look before reporting the work done."""
    from . import taskproofs
    if stale is None:
        stale = {rid for rid, _ in taskproofs.regressions(root, task_rows=rows, fresh_too=True)}
    done = [r for r in [*rows, *taskproofs.archived_tasks(root).values()] if r['Status'] == 'done' and r['ID'] not in stale]
    tested = [r['ID'] for r in done if evidence.acceptance_kind(r) == 'test']
    checked = [r['ID'] for r in done if evidence.acceptance_kind(r) == 'check']
    basis = ([f'{_ids(tested)} by tests'] if tested else []) + \
        ([f'{_ids(checked)} by a check only: a command that exited 0, with the output it names'] if checked else [])
    lines = ['Delivery:', f'  State: {state_text}',
             '  Acceptance: ' + ('; '.join(basis) if basis else 'no current evidence of completed work') + '.', '  ' + host_line(root)]
    if stale:
        lines.append('  Needs verification: ' + _ids(sorted(stale)) + '.')
    found = shortcuts(root, previous, rows)
    if found:
        lines.append('Look at these before reporting the work done; each can make a task easier to pass:')
        lines += [f'  {line}' for line in found[:8]]
    return lines
