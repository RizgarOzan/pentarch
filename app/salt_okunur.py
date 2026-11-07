"""PreToolUse hook (Bash|PowerShell|mcp__.*) for the assistant's own runs; other Claude sessions are not affected.

The core starts each run with the run kind in the environment and loads this hook through salt-okunur.json
(scheduled "otomatik" runs) or eklenti-gorev.json ("görev" task runs).
- Scheduled runs only read: connector tools that send, change or delete, git push/commit and gh writes are denied.
  If such work comes up, the run records it as a task instead.
- Task runs may write (drafts, commits, branches) but not do irreversible outward things: sending or deleting mail,
  answering invites, sharing, push, PR/issue writes. The owner approves the last step from chat.
Reads the hook JSON on stdin; prints a deny decision or nothing. Never fails the tool call on bad input.
"""
import json
import os
import re
import sys
from pathlib import Path

APP = Path(__file__).parent
KIND = os.environ.get("PENTARCH_KIND", "")
TASK = KIND in ("görev", "gorev")

GMAIL = (r"^(send_message|reply|forward|create_draft|update_draft|delete_draft|trash_message|trash_thread|untrash_message|"
         r"untrash_thread|label_message|label_thread|unlabel_message|unlabel_thread|update_message_labels|mark_message_spam|"
         r"mark_thread_spam|unmark_message_spam|unmark_thread_spam|apply_sensitive_message_label|"
         r"apply_sensitive_thread_label|create_label|update_label|delete_label)$")
CALENDAR = r"^(create_event|update_event|delete_event|respond_to_event)$"
DRIVE = r"^(create_file|update_file|trash_file|share_file|copy_file)$"
NOTION = r"^notion-(create|update|delete|move|cancel|restore|upload|send|spawn|stop|duplicate|resolve|set|convert)"
IRREVERSIBLE = (r"^(send_message|reply|forward|trash_message|trash_thread|mark_message_spam|mark_thread_spam|delete_draft|"
                r"delete_label|delete_event|respond_to_event|trash_file|share_file)$|^notion-delete")


def reason(tool, command):
    if tool.startswith("mcp__"):
        m = tool.split("__")[-1]
        if TASK:
            return f"irreversible outward action ({m})" if re.search(IRREVERSIBLE, m, re.I) else None
        if any(re.search(p, m, re.I) for p in (GMAIL, CALENDAR, DRIVE, NOTION)):
            return f"sending/changing/deleting through a connector ({m})"
        return None
    if tool in ("Bash", "PowerShell"):
        c = re.sub(r"\s+", " ", command or "")
        if re.search(r"\bgit\b[^;&|]*\bpush\b", c, re.I):
            return "git push"
        if not TASK and re.search(r"\bgit\b[^;&|]*\bcommit\b", c, re.I):
            return "git commit"
        if re.search(r"\bgh\b[^;&|]*\b(pr|issue|release)\s+(create|comment|merge|close|edit|review)\b", c, re.I):
            return "writing PRs/issues with gh"
        if re.search(r"\bgh\b[^;&|]*\bapi\s.*(-X|--method)\s+(POST|PUT|PATCH|DELETE)\b", c, re.I):
            return "writing through gh api"
    return None


def main():
    if KIND != "otomatik" and not TASK:
        return
    try:
        inp = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        why = reason(str(inp.get("tool_name") or ""), str((inp.get("tool_input") or {}).get("command") or ""))
    except Exception as e:
        why = f"an unreadable tool call ({type(e).__name__})"  # fail closed: a hook that can't read the call blocks it
    if not why:
        return
    if TASK:
        msg = (f"BLOKLU: a task run cannot do {why}. Leave the draft or branch ready; in your final reply say what you "
               "prepared and end it with a [[Send|No]] button; if the owner approves, the chat run does it.")
    else:
        msg = (f"BLOKLU: scheduled runs are read-only, {why} is not allowed. Record the work as a task with "
               f'`python -I "{APP / "pentarch.py"}" gorev "şimdi" "..."`; the task run has write access.')
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": msg}}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
