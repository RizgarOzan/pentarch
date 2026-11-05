"""Provider layer: which AI does the work.

- Agent CLI (config agent.cli): claude, gemini, codex or opencode. Claude Code gets the full path in pentarch.py and
  beyin.py (persistent session, budgets, MCP, resume). The others run through `run_other` below, which keeps
  the Telegram chat in one session per day (gemini --resume, codex exec resume, opencode run --continue).
- Chat API (config chat_api): any OpenAI-compatible /chat/completions endpoint (OpenRouter, Groq, Ollama,
  LM Studio, OpenAI...). Used for cheap one-shot work; when it is not set, `small` falls back to the agent CLI.
"""
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import uuid
from pathlib import Path

from config import C, EXTRA_DIRS, NOTES

CLI = C["agent"]["cli"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def exe(name=None):
    name = name or CLI
    return shutil.which(name) or name


def _yolo():
    return C["agent"]["permission_mode"] == "bypassPermissions"


def other_cmd(prompt, model=None, out_file=None, resume=None, new_id=None):
    """Headless command line for a non-Claude agent CLI.
    resume: session id to continue. new_id: gemini only, the id a new kept session gets.
    codex reports its own id (--json, thread.started); opencode continues the folder's last session."""
    m = ["--model", model] if model else []
    if CLI == "gemini":
        cmd = [exe(), *m, "--approval-mode", "yolo" if _yolo() else "auto_edit"]
        for d in EXTRA_DIRS:
            cmd += ["--include-directories", str(d)]
        if resume:
            cmd += ["--resume", resume]
        elif new_id:
            cmd += ["--session-id", new_id]
        return cmd + ["-p", prompt]
    if CLI == "codex":
        cmd = [exe(), "exec", *m, "--skip-git-repo-check", "--output-last-message", str(out_file), "--json",
               "--dangerously-bypass-approvals-and-sandbox" if _yolo() else "--full-auto"]
        return cmd + (["resume", resume, prompt] if resume else [prompt])
    if CLI == "opencode":
        return [exe(), "run", *m, *(["--continue"] if resume else []), prompt]
    raise ValueError(f"unknown agent cli: {CLI}")


def run_other(prompt, model=None, timeout=3600, cwd=None, resume=None, keep=False):
    """Run on gemini/codex/opencode. Returns the same dict shape claude's JSON output has
    (result, is_error, total_cost_usd, session_id) so the rest of the code does not care which CLI ran.
    keep=True makes the run resumable: session_id comes back and goes into `resume` next time."""
    out_file = Path(tempfile.gettempdir()) / f"pentarch-codex-{os.getpid()}.txt"
    new_id = str(uuid.uuid4()) if keep and not resume and CLI == "gemini" else None
    env = {**os.environ, "GEMINI_CLI_TRUST_WORKSPACE": "true"}  # headless gemini refuses untrusted folders
    try:
        r = subprocess.run(other_cmd(prompt, model, out_file, resume, new_id), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd or NOTES, env=env,
                           creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"{CLI} did not finish in {timeout} s")
    sid = None
    if CLI == "codex":
        text = out_file.read_text(encoding="utf-8").strip() if out_file.exists() else ""
        for line in r.stdout.splitlines():
            if '"thread.started"' in line:
                try:
                    sid = json.loads(line).get("thread_id")
                except ValueError:
                    pass
    else:
        text = r.stdout.strip()
        sid = resume or new_id or ("last" if CLI == "opencode" else None)
    out_file.unlink(missing_ok=True)
    return {"result": text or r.stderr.strip()[-500:], "is_error": r.returncode != 0, "total_cost_usd": 0,
            "session_id": sid if keep else None, "usage": {}}


def chat(messages, model=None, timeout=60, api=None):
    """POST to an OpenAI-compatible endpoint. api = {base_url, model, key_env}; defaults to config chat_api."""
    api = api or C["chat_api"]
    key = os.environ.get(api.get("key_env") or "", "")
    req = urllib.request.Request(api["base_url"].rstrip("/") + "/chat/completions",
                                 json.dumps({"model": model or api["model"], "messages": messages}).encode(),
                                 {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def has_chat_api():
    return bool(C["chat_api"].get("base_url") and C["chat_api"].get("model"))
