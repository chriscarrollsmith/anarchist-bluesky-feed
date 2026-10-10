#!/usr/bin/env python3
"""Gate agent git commits on the same ruff/ty checks as CI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + '\n')
    sys.stdout.flush()


def _allow() -> int:
    _emit({'permission': 'allow'})
    return 0


def _deny(message: str) -> int:
    _emit(
        {
            'permission': 'deny',
            'user_message': message,
            'agent_message': message,
        }
    )
    return 0


def _read_command() -> str:
    raw = sys.stdin.read()
    if not raw.strip():
        return 'git commit'
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 'git commit'
    command = payload.get('command')
    return command if isinstance(command, str) and command.strip() else 'git commit'


def _run_check(label: str, args: list[str], cwd: Path) -> str | None:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
            env={**os.environ, 'NO_COLOR': '1'},
        )
    except OSError as exc:
        return f'pre-commit checks failed ({label}): {exc}'
    if completed.returncode == 0:
        return None
    body = (completed.stdout or '') + (completed.stderr or '')
    return f'pre-commit checks failed ({label}):\n{body[-4000:]}'


def main() -> int:
    command = _read_command()
    if not re.search(r'git\s+commit', command):
        return _allow()

    cwd = Path(__file__).resolve().parents[2]
    uv = shutil.which('uv')
    if not uv:
        for candidate in (
            Path.home() / '.local' / 'bin' / 'uv',
            Path.home() / 'AppData' / 'Local' / 'hermes' / 'bin' / 'uv',
            Path(r'C:\Users\chris\AppData\Local\hermes\bin\uv.exe'),
        ):
            if candidate.is_file():
                uv = str(candidate)
                break
    if not uv:
        return _deny('pre-commit checks: uv not found on PATH (required for ruff/ty).')

    for label, args in (
        ('ruff check', [uv, 'run', 'ruff', 'check', '.']),
        ('ruff format', [uv, 'run', 'ruff', 'format', '--check', '.']),
        ('ty check', [uv, 'run', 'ty', 'check']),
    ):
        err = _run_check(label, args, cwd)
        if err:
            return _deny(err)
    return _allow()


if __name__ == '__main__':
    raise SystemExit(main())
