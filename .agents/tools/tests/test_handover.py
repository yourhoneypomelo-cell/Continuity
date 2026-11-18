"""Field regressions exercised with synthetic data through installed workspace entry points."""
import hashlib
import io
import json
import zipfile

from support import Workspace
from wslib import capture, handover, messages, origin, receipts, reconcile, tables, transcripts


class Conversation(Workspace):
    stamp = '<timestamp>Saturday, Nov 14, 2026, 8:20 PM (UTC+8)</timestamp>'

    def source(self, items):
        path = self.parent / '.cursor/projects/demo/agent-transcripts/trial/trial.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(json.dumps({'role': 'user', 'id': str(i), 'message': {'content': text}})
                                  for i, text in enumerate(items)), encoding='utf-8')
        return path

    def take(self, path):
        return capture.capture(self.root, 'claude', 'Stop', {'session_id': 'trial', 'transcript_path': str(path)})

    def test_source_routes_envelopes_and_preserves_two_equal_user_turns(self):
        items = [self.stamp, self.stamp, self.stamp + '<user_query>' + origin.NOTICE + '</user_query>',
                 origin.WORKER + ' Check the sample.', '<available_subagent_types>x</available_subagent_types>',
                 self.stamp + '<user_query>继续</user_query>', self.stamp + '<user_query>继续</user_query>',
                 self.stamp + '<user_query>Save privately</user_query>', 'Explain <user_query>example</user_query>',
                 origin.NOTICE]
        path = self.source(items)
        result = self.take(path)
        self.assertEqual(result['transcript'], 'docs/chats/cursor/trial.md')
        saved = self.read(result['transcript'])
        rows = messages.entries(saved)
        self.assertEqual([r[-1] for r in rows], ['继续', '继续', 'Save privately', items[-2], origin.NOTICE])
        self.assertEqual(rows[0][2], '2026-11-14T12:20:00Z')
        self.assertNotEqual(rows[0][3], rows[1][3])
        self.take(path)
        self.assertEqual(saved, self.read(result['transcript']))
        data = json.loads(self.read('docs/chats/cursor/raw/trial.origin.json'))
        self.assertEqual((data['host'], data['adapter'], data['session_role']), ('cursor', 'claude', 'worker'))
        self.assertEqual(data['source_events'], {'timestamp': 2, 'host-notice': 1, 'worker-assignment': 1, 'host-capabilities': 1})
        self.assertIn('cursor', self.read('docs/chats/INDEX.md'))
        self.assertIn(rows[-1][3], [m for m, _ in reconcile.pending(self.root)])

    def test_legacy_host_index_keeps_existing_links(self):
        saved = capture.journal(self.root, 'claude', {'session_id': 'trial'}, 'user', 'Save privately')
        path = self.source(['Save privately', self.stamp])
        for _ in range(2):
            result = self.take(path)
        self.assertEqual(result['transcript'], saved['transcript'])
        self.assertIn(saved['id'], self.read(saved['transcript']))
        self.assertIn('# Transcript cursor trial', self.read(saved['transcript']))
        index = tables.parse(self.read('docs/chats/INDEX.md'), capture.INDEX_HEADERS, 'index')
        self.assertEqual([(r['Host'], r['Transcript']) for r in index], [('cursor', saved['transcript'])])
        self.assertFalse((self.root / 'docs/chats/cursor/trial.md').exists())

    def test_legacy_review_filters_metadata_but_keeps_uncertain_prose(self):
        rel = 'docs/chats/cursor/old.md'
        capabilities = ('<available_subagent_types>x</available_subagent_types>\n'
                        '<available_subagent_models>y</available_subagent_models>\n<dynamic_tool_catalog>z</dynamic_tool_catalog>')
        self.write(rel, capture.render('cursor', 'old', [('user', t) for t in
                   (self.stamp, origin.NOTICE, origin.WORKER + ' work', capabilities, 'Review my change')], 'old').replace(transcripts.VISIBLE_MARK, ''))
        capture._index(self.root, 'cursor', 'old', 5, rel, None)
        self.assertEqual([reconcile.texts(self.root / p)[m] for m, p in reconcile.pending(self.root)], ['Review my change'])
        self.assertIn(origin.NOTICE, self.read(rel))
        self.assertEqual(origin.classify('A note with <user_query>quoted words</user_query>')[1],
                         'A note with <user_query>quoted words</user_query>')

    def test_chat_policy_redacts_both_copies_revisions_and_snapshot(self):
        self.init()
        key = 'asp_' + 'a' * 32
        path = self.source(['Please store this ' + key])
        result = self.take(path)
        raw = 'docs/chats/cursor/raw/trial.jsonl'
        for rel in (raw, result['transcript']):
            self.assertNotIn(key, self.read(rel))
            self.assertIn('[REDACTED]', self.read(rel))
        # Simulate one earlier implementation's plaintext copy, then a source edit.
        self.write(result['transcript'], self.read(result['transcript']).replace('[REDACTED]', key))
        self.source(['Different visible request'])
        self.take(path)
        revisions = list((self.root / 'docs/chats/cursor/raw/revisions/trial').glob('*.md'))
        self.assertEqual(len(revisions), 1)
        self.assertNotIn(key, revisions[0].read_text(encoding='utf-8'))
        self.write(raw, json.dumps({'content': 'line one\n' + key}).replace('asp_', '\\u0061sp_') + '\n')
        before = (self.root / raw).read_bytes()
        audit = self.ws('chats', 'audit', expect=1)
        self.assertNotIn(key, audit.stdout + audit.stderr)
        self.assertIn(raw, audit.stdout)
        snap = self.ws('snapshot', '--label', 'before-sharing', raw, expect=2)
        self.assertNotIn(key, snap.stdout + snap.stderr)
        self.assertFalse(list(self.root.rglob('*.partial')))
        self.assertEqual(before, (self.root / raw).read_bytes())

    def test_live_capture_can_be_disabled_independently_of_import(self):
        self.ws('init', '--goal', 'Archive opt in', '--chat-import', 'off', '--chat-capture', 'off')
        path = self.source(['Capture by explicit import only'])
        payload = {'session_id': 'trial', 'transcript_path': str(path), 'prompt': 'Capture by explicit import only'}
        self.assertFalse(capture.submit(self.root, 'claude', payload)['captured'])
        self.assertFalse(self.take(path)['captured'])
        self.assertFalse((self.root / 'docs/chats/cursor').exists())
        self.assertTrue(capture.capture(self.root, 'cursor', 'import', payload)['captured'])
        facts = self.ws('doctor', '--json', expect=None).stdout
        self.assertIn('live chat capture off', facts)
        self.assertIn('import at start off', facts)

    def test_repeated_hook_ids_and_retries(self):
        for mid in ('a', 'b', 'b'):
            capture.journal(self.root, 'cursor', {'session_id': 'trial', 'message_id': mid}, 'user', '继续')
        self.assertEqual(len(messages.entries(self.read('docs/chats/cursor/trial.md'))), 2)
        for stamp in ('2030-01-01T05:00:00Z', '2030-01-01T05:01:00Z', '2030-01-01T05:01:00Z'):
            capture.submit(self.root, 'cursor', {'session_id': 'trial', 'prompt': '继续', 'timestamp': stamp})
        self.assertEqual(len(messages.entries(self.read('docs/chats/cursor/trial.md'))), 4)


class Handoff(Workspace):
    def decision(self, value, *args):
        return self.ws('add', 'decision', '--set', 'decision=' + value, '--set', 'reason=User chose the scope',
                       '--source', 'user', *args)

    def test_new_decision_displaces_old_step_and_links_message(self):
        self.init()
        self.decision('Prepare a public copy')
        self.ws('checkpoint', '--keep', '--stop', 'Prepared options', '--next', 'Wait for a public decision')
        event = capture.journal(self.root, 'cursor', {'session_id': 'trial'}, 'user', 'Save privately first')
        for _ in range(2):
            self.decision('Save privately first', '--supersedes', 'D1', '--message', event['id'], '--next', 'Create the local snapshot')
        self.assertEqual(len(tables.rows(self.root, tables.table_for('decisions'))), 2)
        summary = self.ws('brief').stdout
        self.assertLess(summary.index('D2 adopted: Save privately first'), summary.index('## Handoff'))
        self.assertIn('- next_step: Create the local snapshot', summary)
        self.assertNotIn('-> NOT RECONCILED', self.ws('reconcile', '--review').stdout)
        self.assertEqual(tables.rows(self.root, tables.table_for('decisions'))[0]['Status'], 'superseded')
        detail = json.loads(self.read(handover.LINKS))[-1]
        self.assertEqual((detail['message'], detail['supersedes']), (event['id'], ['D1']))
        self.ws('set', 'D2', '--set', 'decision=Keep it on this machine', '--source', 'user')
        self.assertIn('Earlier handoff next_step (review before use)', self.ws('brief').stdout)
        self.ws('checkpoint', '--keep', '--stop', 'Saved', '--next', 'Create the local snapshot')
        self.assertIn('Earlier handoff next_step', self.ws('brief').stdout)
        self.ws('card', '--set', 'next_step=Create the local snapshot')
        self.assertNotIn('Earlier handoff next_step', self.ws('brief').stdout)
        before = tables.rows(self.root, tables.table_for('decisions'))[-1]
        self.ws('set', 'D2', '--observed', 'Local commit exists. Remote receipt pending.',
                '--artifact', '../snapshots/example @ revision-abcd')
        self.assertEqual(before, tables.rows(self.root, tables.table_for('decisions'))[-1])
        summary = self.ws('brief').stdout
        self.assertIn('Local commit exists. Remote receipt pending.', summary)
        self.assertIn('../snapshots/example @ revision-abcd', summary)
        self.assertIn('supersedes:', summary)

    def test_unlinked_decision_in_legacy_seal_and_expired_observation(self):
        self.init()
        self.save(keep=True)
        self.decision('Approve a private snapshot')
        rows = tables.rows(self.root, tables.table_for('decisions'))
        self.assertEqual(handover.changed(rows, {'ledger': {'D1': 'adopted'}}, {}), [])
        self.assertEqual(handover.changed(rows, {'ledger': {}}, {}), ['D1'])
        self.ws('card', '--set', 'risks=Remote results are provisional', '--risk-until', '2020-01-01T12:00:00Z',
                '--set', 'next_step=Read the receipt')
        summary = self.ws('brief').stdout
        self.assertIn('expired 2020-', summary)
        self.assertIn('observed ', summary)

    def test_recover_only_remaining_batch_in_a_new_session(self):
        self.planned()
        for name, status, remaining in [('alpha', 'done', 'none'), ('beta', 'stopped', 'finish the remaining check')]:
            self.ws('batch', 'set', name, '--task', 'T1', '--status', status, '--stop', 'first check passed',
                    '--next', remaining, '--entry', 'restart.md', '--evidence', 'check.txt', '--artifact', 'snapshot@sample')
        self.save()
        summary = self.ws('brief').stdout
        self.assertIn('T1 beta (stopped)', summary)
        self.assertIn('first check passed | next: finish the remaining check', summary)
        self.assertIn('snapshot@sample', summary)
        self.assertNotIn('T1 alpha (done)', summary)
        self.ws('start')
        self.ws('verify', 'T1', '--done', '--', 'python', '-m', 'unittest', 'test_demo')
        self.ws('batch', 'set', 'beta', '--task', 'T1', '--status', 'done', '--stop', 'all checks passed',
                '--next', 'none', '--entry', 'restart.md')
        self.assertEqual([r['status'] for r in json.loads(self.ws('batch', 'list').stdout)], ['done', 'done'])


class Delivery(Workspace):
    def binding(self, extra=()):
        self.planned()
        self.write('approved.bin', 'approved content')
        self.write('default.bin', 'approved content')
        self.digest = hashlib.sha256((self.root / 'approved.bin').read_bytes()).hexdigest()
        self.args = ('receipt', 'record', 'T1', '--ref', 'external-17', '--scope', 'one component',
                     '--result', 'accepted for this component', '--file', 'approved.bin', '--candidate', 'default.bin',
                     '--sha256', self.digest, *extra)

    def test_green_tests_do_not_verify_a_different_delivery(self):
        self.binding()
        self.ws(*self.args)
        self.ws(*self.args)
        self.assertEqual(len(json.loads(self.ws('receipt', 'list').stdout)), 1)
        self.ws('verify', 'T1', '--done', '--', 'python', '-m', 'unittest', 'test_demo')
        updated = list(self.args)
        updated[updated.index('--ref') + 1] = 'external-18'
        self.ws(*updated)
        self.assertIn('does not cover the current delivery receipt', self.ws('check', expect=1).stdout)
        self.ws('verify', '--stale')
        self.save()
        self.ready()
        self.write('default.bin', 'different bytes')
        self.assertIn('SHA-256', self.ws('receipt', 'check', 'T1', expect=1).stderr +
                      self.ws('receipt', 'check', 'T1', expect=1).stdout)
        self.assertIn('external-18', self.ready(expect=1).stdout)
        self.assertIn('Requirements verified: 0/1', self.ws('brief').stdout)
        self.ws('start')
        failed = self.ws('verify', '--stale', expect=1)
        self.assertIn('external-18', failed.stdout + failed.stderr)
        self.ws('verify', 'T1', '--done', '--because', 'tests still pass', '--', 'python', '-m', 'unittest', 'test_demo', expect=1)
        self.write('default.bin', 'approved content')
        self.ws('receipt', 'check', 'T1')
        self.ws('verify', 'T1', '--done', '--', 'python', '-m', 'unittest', 'test_demo')
        self.save()
        self.ready()
        (self.root / receipts.FILE).unlink()
        self.assertIn('receipt history changed', self.ready(expect=1).stdout)

    def test_trusted_digest_member_and_multiple_scopes(self):
        self.binding(('--container', 'envelope.zip', '--member', 'one/approved.bin'))
        with zipfile.ZipFile(self.root / 'envelope.zip', 'w') as bundle:
            for folder in ('one', 'two'):
                bundle.write(self.root / 'approved.bin', folder + '/approved.bin')
        wrong = list(self.args)
        wrong[wrong.index('--sha256') + 1] = '0' * 64
        self.ws(*wrong, expect=1)
        self.assertFalse((self.root / receipts.FILE).exists())
        self.ws(*self.args)
        other = list(self.args)
        other[other.index('--scope') + 1] = 'another component'
        self.ws(*other)
        self.assertEqual(len(json.loads(self.ws('receipt', 'list', 'T1').stdout)), 2)
        other[other.index('--result') + 1] = 'unsupported replacement'
        self.ws(*other, expect=2)
        with (self.root / 'envelope.zip').open('ab') as stream:
            stream.write(b'changed envelope')
        self.assertIn('container', self.ws('receipt', 'check', 'T1', expect=1).stdout)

    def test_receipt_checked_after_the_command_as_well(self):
        self.binding()
        self.ws(*self.args)
        self.write('change.py', 'from pathlib import Path\nPath("default.bin").write_bytes(b"other")\nprint("OK")\n')
        self.ws('set', 'T1', '--set', 'acceptance=check: python change.py')
        self.ws('verify', 'T1', '--done', '--', 'python', 'change.py', expect=1)
        self.assertNotEqual(tables.rows(self.root, tables.table_for('tasks'))[0]['Status'], 'done')

    def test_final_receipt_closes_only_the_recorded_risk(self):
        self.binding()
        self.ws('card', '--set', 'risks=Results are provisional', '--risk-until', '2030-01-02T00:00:00Z')
        self.ws(*self.args, '--resolve-risk')
        self.assertIn('risks (closed): Closed by T1 receipt external-17', self.ws('brief').stdout)
        history = json.loads(self.ws('receipt', 'list').stdout)[0]['resolved_risk']
        self.assertEqual(history['text'], 'Results are provisional')
        self.assertIn('observed_at', history['observation'])
        self.ws('card', '--set', 'risks=Another delivery is pending')
        self.ws(*self.args, '--resolve-risk')
        self.assertIn('- risks: Another delivery is pending', self.ws('brief').stdout)

    def test_nested_delivery_preflight_catches_credentials_before_copy(self):
        self.binding()
        key = 'asp_' + 'b' * 32
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as archive:
            archive.writestr('visible.jsonl', json.dumps({'content': 'sample\n' + key}).replace('asp_', '\\u0061sp_'))
        with zipfile.ZipFile(self.root / 'envelope.zip', 'w') as outer:
            outer.write(self.root / 'approved.bin', 'receipt/approved.bin')
            outer.writestr('attachments.zip', inner.getvalue())
        report = self.ws('receipt', 'audit', 'envelope.zip', expect=1)
        self.assertIn('envelope.zip!attachments.zip!visible.jsonl', report.stdout)
        refused = self.ws(*self.args, '--container', 'envelope.zip', '--member', 'receipt/approved.bin', expect=2)
        snapshot = self.ws('snapshot', '--label', 'before-delivery', 'envelope.zip', expect=2)
        self.assertNotIn(key, report.stdout + refused.stderr + snapshot.stderr)
        self.assertFalse((self.root / receipts.FILE).exists())
        self.assertFalse(list(self.root.rglob('*.partial')))

    def test_export_checks_the_actual_template_before_creating_either_copy(self):
        key = 'asp_' + 'c' * 32
        target = self.parent / 'portable'
        self.write('AGENTS.md', self.read('AGENTS.md') + '\n' + key + '\n')
        error = self.ws('export', '--output', str(target), '--allow-modified', expect=2)
        self.assertIn('credential in delivery: AGENTS.md', error.stderr)
        self.assertNotIn(key, error.stderr + error.stdout)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_suffix('.zip').exists())
