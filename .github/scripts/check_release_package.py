"""Check the downloaded asset against the tagged receipt and use its native launcher."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile


def check(downloads, tag):
    version = tag.removeprefix('v')
    name = f'agent-workspace-{version}.zip'
    receipt = Path('dist/README.md').read_text(encoding='utf-8')
    expected = re.search(r'^\| SHA-256 \| `([0-9a-f]{64})` \|$', receipt, re.M)
    if not expected or f'| File | `{name}` |' not in receipt or f'| Version | {version} |' not in receipt:
        raise ValueError(f'The tagged receipt does not describe {name}')
    archive = downloads / name
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected[1]:
        raise ValueError(f'{name} has SHA-256 {actual}, expected {expected[1]}')

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / '交接 project'
        project.mkdir()
        if os.name == 'nt':
            with ZipFile(archive) as bundle:
                bundle.extractall(project)
            launcher = project / '.agents/tools/ws.cmd'
        else:
            subprocess.run(['unzip', '-q', str(archive), '-d', str(project)], check=True)
            launcher = project / '.agents/tools/ws'
        env = dict(os.environ, WS_IMPORT='0', WS_HOST_PID=str(os.getpid()), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')

        def ws(*args, expected_code=0, contains=''):
            result = subprocess.run([str(launcher), *args], cwd=project, env=env, capture_output=True,
                                    text=True, encoding='utf-8')
            if result.returncode != expected_code or contains not in result.stdout:
                raise RuntimeError(f'{args} returned {result.returncode}, expected {expected_code} and {contains!r}\n'
                                   f'{result.stdout}{result.stderr}')
            return result.stdout

        ws('--help', contains=f'Continuity workspace tool {version}')
        ws('check', '--strict', contains='Workspace: PASS')
        ws('init', '--goal', 'Deliver a tested CSV export and hand it off')
        ws('check', '--ready', expected_code=1, contains='Workspace: FAIL')
        ws('add', 'requirement', '--set', 'requirement=Export as CSV', '--set', 'acceptance=Export reports CSV')
        ws('add', 'task', '--set', 'requirements=R1', '--set', 'scope=export.py, test_export.py',
           '--set', 'action=Implement CSV export', '--set', 'acceptance=python -m unittest test_export')
        (project / 'export.py').write_text("def export_format():\n    return 'CSV'\n", encoding='utf-8')
        (project / 'test_export.py').write_text(
            "import unittest\nfrom export import export_format\n\nclass Export(unittest.TestCase):\n"
            "    def test_format(self):\n        self.assertEqual(export_format(), 'CSV')\n", encoding='utf-8')
        ws('verify', 'T1', '--done', '--', 'python', '-m', 'unittest', 'test_export')
        ws('add', 'decision', '--set', 'decision=Share the CSV example', '--set', 'reason=Initial scope', '--source', 'user')
        ws('add', 'decision', '--set', 'decision=Keep the CSV format', '--set', 'reason=Consumer format', '--source', 'user')
        ws('batch', 'set', 'export', '--task', 'T1', '--status', 'stopped', '--stop', 'CSV tested',
           '--next', 'Review the example', '--entry', 'test_export.py', '--evidence', 'test_export.py', '--artifact', 'export.py')
        ws('checkpoint', '--keep', '--stop', 'CSV export passed its product test', '--next', 'Share the CSV example')
        ws('set', 'D1', '--set', 'decision=Keep the example local', '--source', 'user')
        ws('checkpoint', '--stop', 'Scope changed', '--next', 'Share the CSV example', contains='NOT READY')
        ws('check', '--ready', expected_code=1, contains='D1')
        ws('start')
        ws('batch', 'set', 'export', '--task', 'T1', '--status', 'done', '--stop', 'Reviewed locally',
           '--next', 'Read the example', '--entry', 'test_export.py')
        batch, = json.loads(ws('batch', 'list', '--task', 'T1', '--history'))
        previous, = batch['history']
        if (batch['status'], previous['status'], batch['evidence'], batch['artifact']) != (
                'done', 'stopped', 'test_export.py', 'export.py'):
            raise RuntimeError(f'Unexpected batch after the scope change: {batch}')
        ws('checkpoint', '--stop', 'Scope reviewed', '--next', 'Review the CSV example locally')
        ws('check', '--ready', contains='Workspace: READY')
        brief = ws('brief', contains='Review the CSV example locally')
        latest = brief.partition('## Latest decision')[2].partition('## ')[0]
        if 'D1 adopted: Keep the example local' not in latest or 'Requirements verified: 1/1' not in brief:
            raise RuntimeError(brief)
    print(f'{name} {actual}: verified R1, the revised decision and next step, and the batch history.')


if __name__ == '__main__':
    check(Path(sys.argv[1]).resolve(strict=True), sys.argv[2])
