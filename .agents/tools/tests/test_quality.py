"""Regression checks for the evidence and conversation failures reproduced on 3.9.1."""

import json
import unittest
from unittest import mock

from support import Workspace
from wslib import capture, core, coverage, delivery, evidence, messages, tables, upgrade
from wslib.schema import CLOSED, TABLES


class Verification(Workspace):
    def test_archived_task_can_be_reverified_without_rewriting_history(self):
        self.done()
        old = tables.rows(self.root, TABLES['tasks'])[0]['Evidence']
        self.save()
        self.ws('start')
        self.ws('compact')
        self.save()
        archive = self.read('docs/archive/closed/T1.md')
        self.ws('start')
        self.write('test_demo.py', self.read('test_demo.py').replace('2 + 2, 4', '2 + 2, 5'))
        self.save()
        self.assertIn('T1', self.ready(expect=1).stdout)
        brief = self.ws('brief').stdout
        self.assertIn('Requirements verified: 0/1', brief)
        self.assertNotIn('T1 by tests', brief)
        self.ws('start')
        self.assertIn('== verify T1', self.ws('verify', '--stale', expect=1).stdout)
        self.passing_test()
        self.assertIn('== verify T1', self.ws('verify', '--stale').stdout)
        self.save()
        self.ready()
        self.assertIn('Requirements verified: 1/1', self.ws('brief').stdout)
        self.assertEqual(self.read('docs/archive/closed/T1.md'), archive)
        self.assertNotIn(old, self.read(CLOSED))
        self.assertTrue((self.root / old).is_file())
        self.assertEqual(tables.rows(self.root, TABLES['tasks']), [])

    def test_later_failure_invalidates_the_old_pass_with_unchanged_files(self):
        self.planned()
        self.write(
            'test_demo.py',
            'import os, unittest\nclass Product(unittest.TestCase):\n'
            '    def test_service(self):\n        self.assertNotEqual(os.getenv("SAMPLE_CHECK_RESULT"), "fail")\n',
        )
        args = ('verify', 'T1', '--done', '--', 'python', '-m', 'unittest', 'test_demo')
        self.ws(*args)
        self.ws(*args, env={'SAMPLE_CHECK_RESULT': 'fail'}, expect=1)
        self.save()
        self.assertIn('latest acceptance failed', self.ready(expect=1).stdout)
        self.assertIn('Requirements verified: 0/1', self.ws('brief').stdout)
        self.ws('start')
        self.ws('verify', '--stale')
        self.save()
        self.ready()

    def test_all_tasks_of_one_requirement_must_be_current(self):
        live = {
            'requirements': [{'ID': 'R1', 'Status': 'active'}],
            'tasks': [{'ID': rid, 'Requirements': 'R1', 'Status': 'done', 'Evidence': 'a run'} for rid in ('T1', 'T2')],
        }
        self.assertEqual(coverage.requirement_coverage(live, [], {'T1'}), (0, 1, ['R1']))
        live['tasks'].pop(0)
        closed = [{'ID': 'T1', 'Summary': 'R1: previously finished', 'Status': 'done', 'Evidence': 'a run'}]
        self.assertEqual(coverage.requirement_coverage(live, closed, {'T1'}), (0, 1, ['R1']))

    def test_feature_waits_for_all_of_its_product_evidence(self):
        self.planned()
        self.passing_test('test_other.py')
        self.ws(
            'add',
            'task',
            '--set',
            'requirements=R1',
            '--set',
            'scope=test_other.py',
            '--set',
            'action=Verify the other part',
            '--set',
            'acceptance=python -m unittest test_other',
        )
        self.ws('set', 'F1', '--set', 'tasks=T1, T2')
        self.ws('verify', 'T1', '--done', '--', 'python', '-m', 'unittest', 'test_demo')
        self.save(keep=True)
        self.write('test_demo.py', self.read('test_demo.py').replace('2 + 2, 4', '2 + 2, 5'))
        self.ws('verify', 'T2', '--done', '--', 'python', '-m', 'unittest', 'test_other')
        self.assertNotIn('| F1 | shipped |', self.read('docs/state/FEATURES.md'))
        self.write('test_demo.py', self.read('test_demo.py').replace('2 + 2, 5', '1 + 3, 4'))
        self.ws('verify', '--stale')
        self.assertIn('| F1 | shipped |', self.read('docs/state/FEATURES.md'))

    def test_upgrade_recovers_a_later_legacy_rejection(self):
        self.planned()
        self.write(
            'test_demo.py',
            'import os, unittest\nclass Demo(unittest.TestCase):\n'
            '    def test_value(self):\n        self.assertNotIn("DEMO_FAIL", os.environ)\n',
        )
        args = ('verify', 'T1', '--done', '--', 'python', '-m', 'unittest', 'test_demo')
        self.ws(*args)
        self.ws(*args, env={'DEMO_FAIL': 'yes'}, expect=1)
        # The old tool retained both run files but never wrote the rejection into state.
        state = core.state_of(self.root)
        del state['rejected_verifications']
        core.save_state(self.root, state)
        self.save()
        upgrade.rebaseline(self.root, [], 'version transition', upgraded={'from': '3.9.1', 'to': '3.9.2'})
        self.assertIn('T1', core.state_of(self.root)['rejected_verifications'])
        self.assertIn('Requirements verified: 0/1', self.ws('brief').stdout)
        self.ws('start')
        self.ws('verify', '--stale')
        self.save()
        self.ready()

    def test_reverification_checks_the_original_archived_definition(self):
        self.done()
        self.ws('compact')
        rel = 'docs/archive/closed/T1.md'
        self.write(rel, self.read(rel).replace('python -m unittest test_demo', 'python -m unittest something_else'))
        result = self.ws('verify', '--stale', expect=1)
        self.assertIn('differs from its original verification', result.stdout)
        self.assertNotIn('== verify T1', result.stdout)

    def test_prune_keeps_the_report_attachment_and_previous_task_runs(self):
        self.init()
        script = (
            'from pathlib import Path\nimport json, os\n'
            'Path(os.environ["CONTINUITY_REPORT"]).write_text(json.dumps({"schema":"test-summary.v1","total":1,"passed":1,"failed":0,'
            '"errors":0,"skipped":0}))\n'
        )
        self.write('product_check.py', script)
        self.ws(
            'add',
            'task',
            '--set',
            'requirements=R1',
            '--set',
            'scope=product_check.py',
            '--set',
            'action=Check a product',
            '--set',
            'acceptance=python product_check.py',
        )
        args = ('verify', 'T1', '--done', '--report', 'json', '--', 'python', 'product_check.py')
        old = self.json(*args)['evidence']
        new = self.json(*args)['evidence']
        self.ws('compact', '--prune')
        for rel in (old, new):
            self.assertTrue(evidence.load(self.root, rel, 'test')['accepted'])


class VisibleConversation(Workspace):
    def capture_records(self, records):
        file = self.parent / 'host.jsonl'
        file.write_text('\n'.join(json.dumps(r) for r in records), encoding='utf-8')
        return capture.capture(self.root, 'codex', 'Stop', {'session_id': 'sample', 'transcript_path': str(file)})

    def test_only_visible_messages_and_question_answers_reach_both_copies(self):
        envelope = (
            '<send_user_message_question_reply>\n'
            + json.dumps(
                [{'questionItemId': 'private-item-metadata', 'question': 'Which format?', 'answer': 'CSV only'}]
            )
            + '\n</send_user_message_question_reply>'
        )
        self.capture_records(
            [
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': envelope}},
                {
                    'type': 'assistant',
                    'message': {
                        'role': 'assistant',
                        'content': [
                            {'type': 'thinking', 'thinking': 'private-marker-A'},
                            {'type': 'text', 'text': 'Recorded CSV.'},
                        ],
                    },
                },
                {
                    'type': 'response_item',
                    'payload': {
                        'type': 'message',
                        'role': 'assistant',
                        'channel': 'analysis',
                        'content': 'private-marker-B',
                    },
                },
                {'type': 'system', 'content': 'private-marker-C'},
            ]
        )
        chat = self.read('docs/chats/codex/sample.md')
        raw = self.read('docs/chats/codex/raw/sample.jsonl')
        for value in ('private-item-metadata', 'private-marker-A', 'private-marker-B', 'private-marker-C'):
            self.assertNotIn(value, chat + raw)
        rows = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual([row['content'] for row in rows], ['Which format?\nCSV only', 'Recorded CSV.'])
        self.assertEqual(len({r['id'] for r in rows}), 2)
        self.assertIsNone(rows[-1]['timestamp'])
        self.assertEqual(rows[-1]['delivery'], 'receipt unknown')
        self.assertIn('CSV only', chat)

    def test_lagging_snapshot_keeps_the_last_correction_and_indexes_the_real_count(self):
        before = [{'role': 'user', 'content': 'Choose CSV'}, {'role': 'assistant', 'content': 'Recorded.'}]
        self.capture_records(before)
        # The prompt hook fires before the host file contains the next message.
        saved = capture.journal(self.root, 'codex', {'session_id': 'sample'}, 'user', 'Correction: include the headers')
        for _ in range(2):
            self.assertEqual(self.capture_records(before)['messages'], 3)
        self.assertIn('| codex | sample | 3 |', self.read('docs/chats/INDEX.md'))
        before.append({'role': 'user', 'content': 'Correction: include the headers'})
        self.capture_records(before)
        chat = self.read('docs/chats/codex/sample.md')
        self.assertEqual(chat.count('Correction: include the headers'), 1)
        self.assertIn(saved['id'], chat)
        self.assertIn('No assistant reply after the last observed user message', chat)

    def test_equal_turns_and_an_edited_instruction_keep_distinct_identities(self):
        records = [
            {'role': 'user', 'content': 'Yes', 'id': 'u1'},
            {'role': 'user', 'content': 'Yes', 'id': 'u2'},
            {'role': 'user', 'content': 'Export JSON', 'timestamp': '2026-11-01T00:00:00Z', 'id': 'u3'},
        ]
        self.capture_records(records)
        path = 'docs/chats/codex/sample.md'
        old = messages.entries(self.read(path))
        self.assertEqual(len({m[3] for m in old}), 3)
        records[-1]['content'] = 'Export CSV'
        self.capture_records(records)
        new = messages.entries(self.read(path))
        self.assertNotEqual(old[-1][3], new[-1][3])
        self.assertEqual(old[:2], new[:2])
        self.assertNotIn('Export JSON', self.read(path))
        history = list((self.root / 'docs/chats/codex/raw/revisions/sample').glob('*.md'))
        self.assertEqual(len(history), 1)
        self.assertIn('Export JSON', history[0].read_text(encoding='utf-8'))
        # Reverting an instruction is another user decision, even if it matches the first wording.
        records[-1]['content'] = 'Export JSON'
        self.capture_records(records)
        reverted = messages.entries(self.read(path))[-1][3]
        self.assertNotIn(reverted, (old[-1][3], new[-1][3]))

    def test_trial_filename_does_not_certify_a_handoff(self):
        self.write('docs/archive/trials/2026-11-18-codex.md', '# Trial to fill in\n')
        with mock.patch('wslib.doctor.current_host', return_value='codex'):
            line = delivery.host_line(self.root)
        self.assertIn('record to inspect', line)
        self.assertNotIn('tried end to end', line)

    def test_host_ids_distinguish_equal_turns_after_insertion(self):
        self.capture_records([{'role': 'user', 'content': 'Okay', 'id': 'original'}])
        raw = 'docs/chats/codex/raw/sample.jsonl'
        original = json.loads(self.read(raw))
        self.capture_records(
            [
                {'role': 'user', 'content': 'Okay', 'id': 'inserted'},
                {'role': 'user', 'content': 'Okay', 'id': 'original'},
            ]
        )
        first, second = [json.loads(line) for line in self.read(raw).splitlines()]
        self.assertEqual([first['source_id'], second['source_id']], ['inserted', 'original'])
        self.assertEqual(second['id'], original['id'])
        self.assertNotEqual(first['id'], original['id'])

    def test_desktop_visible_only_question_and_dual_stream_attachments(self):
        def ui(kind, text, identifier):
            part = 'text' if kind == 'UserMessage' else 'Text'
            return {
                'type': 'event_msg',
                'payload': {
                    'type': 'item_completed',
                    'item': {'type': kind, 'id': identifier, 'content': [{'type': part, 'text': text}]},
                },
            }

        header = '# Files mentioned by the user:\n\n## My request:\n'
        attachment = '\n<image name=[Image #1] path="E:/private/example.png">\n</image>'
        response = {
            'type': 'response_item',
            'payload': {'type': 'message', 'role': 'user', 'content': header + 'Keep this logo.' + attachment},
        }
        rows = [
            response,
            ui('UserMessage', header + 'Keep this logo.', 'u0'),
            ui('AgentMessage', 'Which version do you want?', 'a0'),
        ]
        self.capture_records(rows)
        raw = self.read('docs/chats/codex/raw/sample.jsonl')
        self.assertNotIn('E:/private', raw)
        self.assertEqual(
            [(r['content'], r['source_id']) for r in map(json.loads, raw.splitlines())],
            [('Keep this logo.', 'u0'), ('Which version do you want?', 'a0')],
        )

    def test_explicit_host_rewind_keeps_removed_turns_in_history_only(self):
        turns = [
            {'$set': {'messages': [{'id': 'a', 'type': 'user', 'content': 'Keep CSV'}]}},
            {'id': 'b', 'type': 'user', 'content': 'Also add a fax export'},
        ]
        self.capture_records(turns)
        self.capture_records(turns + [{'$rewindTo': 'b'}])
        self.assertEqual([r[4] for r in messages.entries(self.read('docs/chats/codex/sample.md'))], ['Keep CSV'])
        archives = list((self.root / 'docs/chats/codex/raw/revisions/sample').glob('*.md'))
        self.assertEqual(len(archives), 1)
        self.assertIn('fax export', archives[0].read_text(encoding='utf-8'))

    def test_a_substantive_extension_needs_a_fresh_reconciliation(self):
        capture.journal(self.root, 'codex', {'session_id': 'sample'}, 'user', 'Export CSV')
        rel = 'docs/chats/codex/sample.md'
        first_id = messages.entries(self.read(rel))[0][3]
        self.capture_records([{'role': 'user', 'content': 'Export CSV without prices'}])
        current = messages.entries(self.read(rel))
        self.assertEqual([r[4] for r in current], ['Export CSV without prices'])
        self.assertNotEqual(first_id, current[0][3])

    def test_repeated_reply_after_a_new_question_is_saved(self):
        path = self.parent / 'capture.jsonl'
        turns = [
            {'role': 'user', 'content': 'First?'},
            {'role': 'assistant', 'content': 'Yes.'},
            {'role': 'user', 'content': 'Second?'},
        ]
        path.write_text('\n'.join(map(json.dumps, turns)), encoding='utf-8')
        payload = {'session_id': 'sample', 'transcript_path': str(path), 'last_assistant_message': 'Yes.'}
        for _ in range(2):
            result = capture.capture(self.root, 'claude', 'Stop', payload)
            self.assertEqual(result['messages'], 4)
        text = self.read('docs/chats/claude/sample.md')
        self.assertEqual([row[4] for row in messages.entries(text)], ['First?', 'Yes.', 'Second?', 'Yes.'])
        self.assertEqual(len({row[3] for row in messages.entries(text)}), 4)


if __name__ == '__main__':
    unittest.main()
