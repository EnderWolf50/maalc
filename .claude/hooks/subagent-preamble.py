"""SubagentStart: hand every subagent the repo's working rules (docs/agents/subagent-preamble.md)."""
import json
from pathlib import Path

doc = Path(__file__).resolve().parents[2] / "docs/agents/subagent-preamble.md"
if doc.is_file():
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                             "additionalContext": doc.read_text(encoding="utf-8")}}))
