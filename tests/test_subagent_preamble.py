"""The actual SubagentStart hook forwards the machine-local storage instructions."""
import json
from pathlib import Path
import subprocess
import sys


def test_hook_passes_main_checkout_storage_and_migration_rules():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / '.claude/hooks/subagent-preamble.py')],
                            capture_output=True, text=True, encoding='utf-8', check=True)
    context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert 'tools/local_dir.py' in context and '.local/probe/' in context
    assert '.local/scratch/' in context and '.local/archive/' in context
    assert 'independent source writers are idle' in context
