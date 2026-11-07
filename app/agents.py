"""Provider layer: which AI does the work.

- Agent CLI (config agent.cli): claude, gemini, codex or opencode. Claude Code gets the full path in pentarch.py and
  beyin.py (persistent session, budgets, MCP, resume). The others run through `run_other` below, which keeps
  the Telegram chat in one session per day (gemini --resume, codex exec resume, opencode run --continue).
- Chat API (config providers, or the older single chat_api): OpenAI-compatible /chat/completions endpoints
  (OpenRouter, Groq, Ollama, LM Studio, OpenAI...), tried in order. Used for cheap one-shot work; when none is set
  or all fail, callers fall back to the agent CLI.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from config import C, EXTRA_DIRS, NOTES, SECRETS, T

CLI = C["agent"]["cli"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def exe(name=None):
    name = name or CLI
    return shutil.which(name) or name


def _yolo():
    """Sandbox-free codex / gemini yolo only when setup recorded an explicit second confirmation."""
    a = C["agent"]
    return a["permission_mode"] == "bypassPermissions" and a.get("bypass_confirmed") is True


def other_cmd(prompt, model=None, out_file=None, resume=None, new_id=None, cli=None):
    """Headless command line for a non-Claude agent CLI.
    resume: session id to continue. new_id: gemini only, the id a new kept session gets.
    codex reports its own id (--json, thread.started); opencode continues the folder's last session."""
    cli = cli or CLI
    m = ["--model", model] if model else []
    if cli == "gemini":
        cmd = [exe(cli), *m, "--approval-mode", "yolo" if _yolo() else "auto_edit", "--skip-trust"]
        for d in EXTRA_DIRS:
            cmd += ["--include-directories", str(d)]
        if resume:
            cmd += ["--resume", resume]
        elif new_id:
            cmd += ["--session-id", new_id]
        return cmd + ["-p", prompt]
    if cli == "codex":
        cmd = [exe(cli), "exec", *m, "--skip-git-repo-check", "--output-last-message", str(out_file), "--json",
               "--dangerously-bypass-approvals-and-sandbox" if _yolo() else "--full-auto"]
        return cmd + (["resume", resume, prompt] if resume else [prompt])
    if cli == "opencode":
        return [exe(cli), "run", *m, *(["--continue"] if resume else []), prompt]
    raise ValueError(f"unknown agent cli: {cli}")


def run_other(prompt, model=None, timeout=3600, cwd=None, resume=None, keep=False, cli=None):
    """Run on gemini/codex/opencode. Returns the same dict shape claude's JSON output has
    (result, is_error, total_cost_usd, session_id) so the rest of the code does not care which CLI ran.
    keep=True makes the run resumable: session_id comes back and goes into `resume` next time."""
    cli = cli or CLI
    out_file = Path(tempfile.gettempdir()) / f"pentarch-codex-{uuid.uuid4().hex}.txt"  # unique: parallel runs share a PID
    new_id = str(uuid.uuid4()) if keep and not resume and cli == "gemini" else None
    env = {**os.environ, "GEMINI_CLI_TRUST_WORKSPACE": "true"}  # headless gemini refuses untrusted folders
    try:
        r = subprocess.run(other_cmd(prompt, model, out_file, resume, new_id, cli), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd or (NOTES if NOTES.is_dir() else None), env=env,
                           creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"{cli} did not finish in {timeout} s")
    sid = None
    if cli == "codex":
        text = out_file.read_text(encoding="utf-8").strip() if out_file.exists() else ""
        for line in r.stdout.splitlines():
            if '"thread.started"' in line:
                try:
                    sid = json.loads(line).get("thread_id")
                except ValueError:
                    pass
    else:
        text = r.stdout.strip()
        sid = resume or new_id or ("last" if cli == "opencode" else None)
    out_file.unlink(missing_ok=True)
    # stderr is never the answer: an empty run is an error with a marker, stderr goes to "error" for the log
    return {"result": text or T(f"(hata: {cli} cevap vermedi)", f"(error: {cli} gave no answer)"),
            "is_error": r.returncode != 0 or not text, "total_cost_usd": 0,
            "session_id": sid if keep else None, "usage": {}, "error": r.stderr.strip()[-500:]}


SECRET_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9]{20,}|nvapi-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}"
                       r"|github_pat_[A-Za-z0-9_]{30,}|AIza[0-9A-Za-z_-]{35,}|AKIA[0-9A-Z]{16}|xox[abp]-[A-Za-z0-9-]{10,}"
                       r"|\d{8,10}:[A-Za-z0-9_-]{35,})")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")
KART_RE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")  # card-like: 13-19 digits
TEL_RE = re.compile(r"(?<![\w])\+?\(?\d{1,4}\)?(?:[ .-]?\(?\d{2,4}\)?){2,5}(?![\w])")


def redact(text, kisisel=False):
    """Masks keys and tokens before text goes to an API model: the values in secrets/keys.env, then known key shapes.
    kisisel=True also masks e-mail addresses, IBAN/card-like numbers and phone numbers."""
    if not isinstance(text, str):
        return text
    f = SECRETS / "keys.env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            v = line.partition("=")[2].strip().strip('"')
            if len(v) >= 12:
                text = text.replace(v, "[secret]")
    text = SECRET_RE.sub("[secret]", text)
    if kisisel:
        text = EMAIL_RE.sub("[e-posta]", text)
        text = IBAN_RE.sub("[iban]", text)
        text = KART_RE.sub("[numara]", text)
        text = TEL_RE.sub(lambda m: "[telefon]" if sum(c.isdigit() for c in m[0]) >= 7 else m[0], text)
    return text


def providers():
    """Ordered OpenAI-compatible endpoints: config "providers", or the single older chat_api when that is set."""
    liste = [p for p in C.get("providers") or [] if p.get("base_url") and p.get("model")]
    if not liste and C["chat_api"].get("base_url") and C["chat_api"].get("model"):
        liste = [C["chat_api"]]
    return liste


def guvensiz(api):
    """Free or data-training providers, and (default-deny) any provider not marked trusted."""
    if api.get("free") or api.get("trains_on_data"):
        return True
    return C.get("privacy", {}).get("default_deny", True) and not api.get("trusted")


def istek(api, messages, model=None, timeout=60, max_tokens=None, deneme=3, kisisel=False):
    """One POST with retries. Returns (text, usage). 429/5xx/timeouts are retried with backoff (Retry-After honoured);
    on 429 the provider's fallback_model is tried first when configured. Untrusted providers only get redacted text,
    and none of the owner's profile/CV/notes (kisisel=True) when privacy.block_personal is on."""
    pii = guvensiz(api)
    if pii and kisisel and C.get("privacy", {}).get("block_personal", True):
        raise PermissionError(f"{api['base_url']}: personal data is not sent to an untrusted provider")
    key = os.environ.get(api.get("key_env") or "", "")
    models = (model or api["model"]).split(",")  # "a,b": OpenRouter tries b when a is rate-limited
    govde = {"model": models[0], **({"models": models} if len(models) > 1 else {}),
             **({"max_tokens": max_tokens} if max_tokens else {}),
             "messages": [{**m, "content": redact(m["content"], pii)} for m in messages]}
    hata = None
    for i in range(deneme):
        req = urllib.request.Request(api["base_url"].rstrip("/") + "/chat/completions", json.dumps(govde).encode(), {
            "Content-Type": "application/json", "User-Agent": "pentarch/1.0",  # Groq 403s urllib's default agent
            **({"Authorization": f"Bearer {key}"} if key else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read())
            text = (j["choices"][0]["message"]["content"] or "").strip()
            if not text:
                raise RuntimeError(f"{api['base_url']}: empty answer")
            return text, j.get("usage") or {}
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise RuntimeError(f"{api['base_url']} HTTP {e.code}: {e.read()[:200]!r}") from e
            hata = f"HTTP {e.code}"
            if e.code == 429 and api.get("fallback_model") and govde["model"] != api["fallback_model"]:
                govde["model"] = api["fallback_model"]  # e.g. Gemini Flash -> Flash-Lite, no wait
                govde.pop("models", None)
                continue
            bekle = e.headers.get("Retry-After") if e.headers else None
        except (urllib.error.URLError, TimeoutError) as e:
            hata, bekle = repr(e), None
        if i < deneme - 1:
            try:
                bekle = min(float(bekle), 30)
            except (TypeError, ValueError):
                bekle = 2 ** i
            time.sleep(bekle)
    raise RuntimeError(f"{api['base_url']}: no answer after {deneme} tries ({hata})")


def chat(messages, model=None, timeout=60, api=None, kisisel=False):
    """POST to OpenAI-compatible endpoints: the given api, else each of providers() in order until one answers."""
    hatalar = []
    for p in [api] if api else providers():
        try:
            return istek(p, messages, model if api else None, timeout, kisisel=kisisel)[0]
        except Exception as e:  # next provider
            hatalar.append(str(e)[:200])
    raise RuntimeError("all chat providers failed: " + " | ".join(hatalar or ["none configured"]))


def has_chat_api():
    return bool(providers())


def mcp_dosyasi():
    """config mcp_servers as a Claude Code --mcp-config file in the runtime home, or None when none are set.
    Only variable names go in the file (${NAME}); values stay in the environment."""
    servers = C.get("mcp_servers") or {}
    if not servers:
        return None
    out = {ad: {"command": s["command"], "args": list(s.get("args") or []),
                **({"env": {v: "${" + v + "}" for v in s["env"]}} if s.get("env") else {})}
           for ad, s in servers.items() if s.get("command")}
    f = SECRETS.parent / "mcp-servers.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"mcpServers": out}, indent=1), encoding="utf-8")
    return f

