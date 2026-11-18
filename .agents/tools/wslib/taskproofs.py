"""Freshness of the evidence for work that still serves an active requirement."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import evidence, tables
from .core import (WorkspaceError, checkpoint_of, describe_drift, difference, digest, fingerprint, read, rewatch,
                   source_path, state_of)
from .schema import NONE, TABLES


def archived_tasks(root: Path, closed=None) -> dict:
    """Archived task definitions and their current evidence pointer. Keep the archived original untouched."""
    closed = tables.closed_rows(root) if closed is None else closed
    done = [r for r in closed if r['ID'].startswith('T') and r['Status'] == 'done'
            and not r.get('Evidence', '').startswith('v2:')]
    if not done:
        return {}
    active = {r['ID'] for r in tables.rows(root, TABLES['requirements']) if r['Status'] == 'active'}
    if not active:
        return {}
    found = {}
    for entry in done:
        rid = entry['ID']
        rel = f'docs/archive/closed/{rid}.md'
        cited = set(re.findall(r'\bR[1-9]\d*\b', entry['Summary'].partition(':')[0]))
        if ':' in entry['Summary'] and cited and not active & cited:
            continue
        try:
            if not tables.ID_RE.fullmatch(rid) or entry.get('Row') != rel:
                raise WorkspaceError('no archived task definition')
            rows = tables.parse(read(root, rel), TABLES['tasks'].headers, rel, 'T')
            if len(rows) != 1 or rows[0]['ID'] != rid or rows[0]['Status'] != 'done':
                raise WorkspaceError('the archived task definition does not match its ID and status')
            row = rows[0]
            original = evidence.evidence_paths(row.get('Evidence', NONE))
            if not original:
                raise WorkspaceError('no original verification to bind the archived command')
            proof = evidence.load(root, original[-1], evidence.acceptance_kind(row))
            if proof.get('task_definitions', {}).get(rid) != evidence.task_definition(row):
                raise WorkspaceError('the archived command or task definition differs from its original verification')
            cited = set(tables.refs(row['Requirements'], 'R'))
        except (OSError, ValueError) as error:
            row = {'ID': rid, 'Status': 'done', 'archive_error': f'{rid}: {error}. Restore the original task row at {rel}'}
        if active & cited:
            found[rid] = {**row, 'Evidence': entry['Evidence'], '_closed': entry}
    return found


def task_rows(root: Path) -> dict:
    return {**archived_tasks(root), **{r['ID']: r for r in tables.rows(root, TABLES['tasks'])}}


def prior_rejections(root: Path) -> dict:
    """Recover later rejected runs from installations that only attached successful evidence to the task."""
    latest, definitions = {}, {}
    for rid, row in task_rows(root).items():
        paths = evidence.evidence_paths(row.get('Evidence', NONE))
        if row['Status'] != 'done' or not paths or row.get('archive_error'):
            continue
        try:
            proof = evidence.load(root, paths[-1], evidence.acceptance_kind(row))
        except (OSError, ValueError):
            continue
        latest[rid] = proof.get('revision', -1)
        definitions[rid] = evidence.task_definition(row)
    found = {}
    if latest:
        for path in sorted((root / 'docs/archive/checks').glob('*.json')):
            rel = path.relative_to(root).as_posix()
            if not evidence.EVIDENCE_RE.fullmatch(rel):
                continue
            try:
                run = json.loads(read(root, rel))
            except (OSError, ValueError):
                continue
            if not isinstance(run, dict) or run.get('schema') != 'verification.v5' or run.get('accepted') is not False:
                continue
            for rid in run.get('for_tasks') or []:
                if rid in latest and run.get('task_definitions', {}).get(rid) == definitions[rid] and (
                        isinstance(run.get('revision'), int) and run['revision'] > latest[rid]):
                    latest[rid], found[rid] = run['revision'], rel
    return found


def fresh(cp, row: dict) -> bool:
    rid = row['ID']
    return (((cp or {}).get('ledger') or {}).get(rid) != 'done'
            or ((cp or {}).get('task_definitions') or {}).get(rid) != evidence.task_definition(row)
            or ((cp or {}).get('task_evidence') or {}).get(rid) != row.get('Evidence'))


def drift(root: Path, row: dict, proof: dict, current_files: dict):
    documents = evidence.document_scope([row])
    missing = sorted(set(documents) - set(proof.get('document_scope', ())))
    if missing:
        return 'no verification baseline for ' + ', '.join(missing[:6])
    current_files = {p: value for p, value in current_files.items() if source_path(p, documents)}
    if proof.get('source') == digest(current_files):
        return None
    if not isinstance(proof.get('source_files'), dict):
        return 'unknown'
    recorded = rewatch(root, proof['source_files'], source_only=True, documents=documents)
    diff = difference(recorded, current_files)
    scope = evidence.scope_paths(row, set(current_files) | set(recorded), acceptance=True)
    if scope is not None:
        diff = {k: [n for n in v if evidence.in_scope(n, scope)] for k, v in diff.items()}
    return describe_drift(diff, 6) if any(diff.values()) else None


def regressions(root: Path, cp=None, task_rows=None, current_files=None, fresh_too=False) -> list:
    """Tasks whose latest evidence cannot support a current requirement. A seal never resets a rejection."""
    state = state_of(root)
    if cp is None and state.get('checkpoint'):
        cp = checkpoint_of(root, state)
    live = tables.rows(root, TABLES['tasks']) if task_rows is None else task_rows
    rows = [r for r in live if r['Status'] == 'done'] + list(archived_tasks(root).values())
    if not rows:
        return []
    if current_files is None:
        current_files = fingerprint(root, source_only=True, documents=evidence.document_scope(rows))
    found = []
    from . import receipts
    bound = receipts.current(receipts.records(root, cp or {}), {r['ID'] for r in rows})
    bindings = receipts.proof_bindings(bound)
    mismatches = dict(receipts.failures(root, bound))
    rejected = state.get('rejected_verifications') or {}
    for row in rows:
        rid = row['ID']
        reason = row.get('archive_error') or mismatches.get(rid)
        if not reason and rid in rejected:
            reason = 'latest acceptance failed: ' + rejected[rid]
        if not reason and rid not in bindings and '_closed' not in row and fresh(cp, row) and not fresh_too:
            continue
        if not reason:
            paths = evidence.evidence_paths(row.get('Evidence', NONE))
            if not paths:
                reason = 'missing acceptance evidence'
            for rel in paths:
                try:
                    proof = evidence.load(root, rel, evidence.acceptance_kind(row))
                    if ('for_tasks' in proof and rid not in proof['for_tasks']) or (
                            rid in proof.get('task_definitions', {}) and
                            proof['task_definitions'][rid] != evidence.task_definition(row)):
                        reason = 'the proof belongs to another task or an earlier definition'
                    else:
                        reason = receipts.proof_problem(proof, rid, bindings) or drift(root, row, proof, current_files)
                except (OSError, ValueError) as error:
                    reason = str(error)
                if reason:
                    break
        if reason:
            found.append((rid, reason))
    return found
