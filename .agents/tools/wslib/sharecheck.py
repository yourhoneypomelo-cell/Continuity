"""Read-only credential preflight for files and nested delivery ZIPs. Findings never contain values."""
from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path

from .core import WorkspaceError, linked, safe_path
from .redaction import INVISIBLE, TOKEN_PATTERN, redact, token_kind

CHUNK = 128 * 1024
OVERLAP = 2048
ASCII_ESCAPE = re.compile(r'\\u00([0-7][0-9a-fA-F])')


def _kinds(block):
    text = block.decode('utf-8', errors='replace')
    text = ASCII_ESCAPE.sub(lambda m: chr(int(m[1], 16)), text) if '\\u00' in text else text
    return {token_kind(m[0]) for m in TOKEN_PATTERN.finditer(INVISIBLE.sub('', text))}


class Audit:
    def __init__(self):
        self.entries = 0
        self.expanded = 0
        self.issues = []

    def entry(self, stream, name, depth=0):
        self.entries += 1
        if self.entries > 30000 or depth > 6:
            raise WorkspaceError('delivery audit exceeded its archive depth or entry limit')
        start = stream.read(4)
        is_zip = start.startswith((b'PK\x03\x04', b'PK\x05\x06')) or name.lower().endswith('.zip')
        if is_zip:
            if depth:
                # ZIP needs random access. Keep nested bytes only in memory and bound each one.
                blob = start + stream.read(64 * 1024 * 1024)
                if stream.read(1):
                    raise WorkspaceError('nested delivery ZIP exceeds the 64 MiB inspection limit')
                stream = io.BytesIO(blob)
            else:
                stream.seek(0)
            with zipfile.ZipFile(stream) as archive:
                for member in archive.infolist():
                    path = f'{name}!{member.filename}'
                    self.inspect_name(path)
                    if member.is_dir():
                        continue
                    self.expanded += member.file_size
                    if self.expanded > 1024 ** 3:
                        raise WorkspaceError('delivery audit exceeds 1 GiB of expanded ZIP members')
                    with archive.open(member) as part:
                        self.entry(part, path, depth + 1)
            return
        kinds, previous = set(), start
        while True:
            data = stream.read(CHUNK)
            kinds.update(_kinds(previous + data))
            if not data:
                break
            previous = (previous + data)[-OVERLAP:]
        if kinds:
            self.issues.append({'path': redact(name), 'kinds': sorted(kinds)})

    def inspect_name(self, name):
        kinds = _kinds(name.encode('utf-8'))
        if kinds:
            self.issues.append({'path': '[redacted file name]', 'kinds': sorted(kinds)})

    def file(self, stream, name):
        self.inspect_name(name)
        try:
            self.entry(stream, name)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
            # A ZIP decoder can include a raw member name in its error.
            raise WorkspaceError(f'could not fully inspect {redact(name)}: {redact(str(error))}') from None


def inspect(root, rel):
    target = safe_path(root, rel)
    audit = Audit()
    if target.is_file():
        with target.open('rb') as stream:
            audit.file(stream, rel)
    elif target.is_dir():
        for base, dirs, names in os.walk(target):
            here = Path(base)
            if any(linked(here / name) for name in [*dirs, *names]):
                raise WorkspaceError(f'linked entry in delivery folder {redact(here.relative_to(root).as_posix())}')
            for name in sorted(names):
                path = here / name
                with path.open('rb') as stream:
                    audit.file(stream, path.relative_to(root).as_posix())
    else:
        raise WorkspaceError('delivery audit needs an existing file or directory')
    return {'entries': audit.entries, 'findings': audit.issues}


def require_clean(report):
    if report['findings']:
        first = report['findings'][0]
        raise WorkspaceError(f'credential in delivery: {first["path"]} ({", ".join(first["kinds"])}). Inspect the delivery before copying it')


def require_safe_bytes(name, data):
    audit = Audit()
    audit.file(io.BytesIO(data), name)
    require_clean({'findings': audit.issues})
