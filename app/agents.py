"""Provider layer: which AI does the work.

- Agent CLI (config agent.cli): claude, gemini, codex or opencode. Claude Code gets the full path in pentarch.py and
  beyin.py (persistent session, budgets, MCP, resume). The others run through `run_other` below, which keeps
  the Telegram chat in one session per day (gemini --resume, codex exec resume, opencode run --session).
- Chat API (config providers, or the older single chat_api): OpenAI-compatible /chat/completions endpoints
  (OpenRouter, Groq, Ollama, LM Studio, OpenAI...), tried in order. Used for cheap one-shot work; when none is set
  or all fail, callers fall back to the agent CLI.
"""
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from config import C, EXTRA_DIRS, HOME, NOTES, SECRETS, T, agent_env

CLI = C["agent"]["cli"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def browser():
    """Edge or Chrome/Chromium on this machine, or None. Opens the panel as an app window and prints CVs to PDF."""
    pf = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for b in [*(Path(d) / "Microsoft/Edge/Application/msedge.exe" for d in pf if d),
              *(Path(d) / "Google/Chrome/Application/chrome.exe" for d in pf if d),
              *(Path(w) for w in map(shutil.which, ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome")) if w),
              Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
              Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]:
        if b.exists():
            return b
    return None


def exe(name=None):
    name = name or CLI
    return shutil.which(name) or name


def _yolo():
    """Sandbox-free codex / gemini yolo only when setup recorded an explicit second confirmation."""
    a = C["agent"]
    return a["permission_mode"] == "bypassPermissions" and a.get("bypass_confirmed") is True


def other_cmd(model=None, out_file=None, resume=None, new_id=None, cli=None, salt_okur=False, ek=(), oto=False):
    """Headless command line for a non-Claude agent CLI. The prompt goes in on stdin, never as an argument: on Windows
    the npm .cmd shims cut an argument at its first newline and cmd.exe stops at 8191 characters.
    resume: session id to continue. new_id: gemini only, the id a new kept session gets.
    codex and opencode report their own id in their JSON output.
    salt_okur: for prompts carrying outside text; gemini asks for every tool (headless, so nothing runs that
    needs approval), codex gets its read-only sandbox, and no extra folders are added.
    ek: extra codex flags (the MCP -c overrides from mcp_diger).
    oto: a scheduled run (routine, brief): the CLI's own tools only read, like claude's read-only hook; folders and
    MCP servers stay. opencode has no read-only mode."""
    cli = cli or CLI
    m = ["--model", model] if model else []
    if cli == "gemini":
        mode = "default" if salt_okur or oto else "yolo" if _yolo() else "auto_edit"
        cmd = [exe(cli), *m, "--approval-mode", mode, "--skip-trust"]
        # gelen/: files sent over Telegram land there, outside the notes folder gemini is limited to
        for d in [] if salt_okur else [*EXTRA_DIRS, HOME / "gelen"]:
            cmd += ["--include-directories", str(d)]
        if salt_okur:  # the user's own MCP servers (~/.gemini/settings.json) too: allow only a name nobody has
            cmd += ["--allowed-mcp-server-names", "pentarch-hicbiri"]
        if resume:
            cmd += ["--resume", resume]
        elif new_id:
            cmd += ["--session-id", new_id]
        return cmd  # piped stdin with no -p is the headless prompt
    if cli == "codex":
        cmd = [exe(cli), "exec", *m, *ek, "--skip-git-repo-check", "--output-last-message", str(out_file), "--json",
               # MCP tool calls run outside codex's sandbox, so outside text also loses ~/.codex/config.toml's servers
               *(["--sandbox", "read-only", "-c", "mcp_servers={}"] if salt_okur else ["--sandbox", "read-only"] if oto else
                 ["--dangerously-bypass-approvals-and-sandbox"] if _yolo() else ["--full-auto"])]
        return cmd + (["resume", resume, "-"] if resume else ["-"])  # "-": read the prompt from stdin
    if cli == "opencode":  # no message argument: stdin is the message. "last" is what older installs saved
        devam = ["--continue"] if resume == "last" else ["--session", resume] if resume else []
        return [exe(cli), "run", *m, "--format", "json", *devam]
    raise ValueError(f"unknown agent cli: {cli}")


def opencode_json(out):
    """(answer, session id) from `opencode run --format json`: one event per line, the session id on each, text in
    part.text (pieces of one message share a messageID). The answer is the last message's text, as claude reports it.
    Output that isn't JSON (an older opencode) is the answer itself."""
    sid, mesajlar = None, {}
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        sid = sid or ev.get("sessionID")
        p = ev.get("part") or {}
        if ev.get("type") == "text" and isinstance(p.get("text"), str):
            mesajlar[p.get("messageID")] = mesajlar.get(p.get("messageID"), "") + p["text"]
    if sid is None and not mesajlar:
        return out.strip(), None
    return (list(mesajlar.values())[-1].strip() if mesajlar else ""), sid


def run_other(prompt, model=None, timeout=3600, cwd=None, resume=None, keep=False, cli=None, salt_okur=False, oto=False,
              kind=None):
    """Run on gemini/codex/opencode, or on the API brain (cli "api", api_ajan.py). Returns the same dict shape claude's
    JSON output has (result, is_error, total_cost_usd, session_id) so the rest of the code does not care which CLI ran.
    keep=True makes the run resumable: session_id comes back and goes into `resume` next time.
    kind: PENTARCH_KIND for the run, so `pentarch.py routine add` from an agent becomes a Yes/No, as under claude."""
    cli = cli or CLI
    if cli == "api":
        import api_ajan
        return api_ajan.calistir(prompt, timeout, resume, keep, salt_okur, oto, kind)
    tmp = HOME / "tmp"  # inside the private home, not the shared temp folder other users can read
    tmp.mkdir(exist_ok=True)
    out_file = tmp / f"pentarch-codex-{uuid.uuid4().hex}.txt"  # unique: parallel runs share a PID
    new_id = str(uuid.uuid4()) if keep and not resume and cli == "gemini" else None
    ek, ek_env = ([], {}) if salt_okur else mcp_diger(cli)  # outside text gets no MCP tools, as with claude
    env = agent_env(GEMINI_CLI_TRUST_WORKSPACE="true", **ek_env,  # headless gemini refuses untrusted folders
                    **({"PENTARCH_KIND": kind} if kind else {}))
    try:
        r = subprocess.run(other_cmd(model, out_file, resume, new_id, cli, salt_okur, ek, oto), input=prompt, capture_output=True, text=True,
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
    elif cli == "opencode":
        text, sid = opencode_json(r.stdout)
        sid = sid or resume
    else:
        text = r.stdout.strip()
        sid = resume or new_id
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
BEARER_RE = re.compile(r"(?i)\bbearer\s+[\w.~+/=-]{8,}")
PAROLA_RE = re.compile(r"(?i)\b(password|passwd|parola|şifre)(\s*[:=]\s*)\S+|\b(pass)(\s*=\s*)\S+")
# "key: sk-..." / "token=..." from a provider with no known key shape; 16+ characters so "key: the plan" stays
ANAHTAR_RE = re.compile(r"(?i)\b((?:api[_-]?)?key|token|secret|anahtar)(\s*[:=]\s*)\S{16,}")
_EV = Path.home()
EV_RE = re.compile("(?:" + re.escape(str(_EV)).replace(r"\\", r"[\\/]") + "|" + re.escape(_EV.as_posix()) + r")(?![\w.-])",
                   re.I) if len(_EV.parts) > 1 else None  # the home folder path names the OS user


def redact(text, kisisel=False):
    """Masks keys and tokens before text goes to an API model: the values in secrets/keys.env, known key shapes,
    `Bearer <token>`, values after password:/şifre:/pass=, and the home-folder path (it names the OS user).
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
    text = BEARER_RE.sub("Bearer [secret]", text)
    text = PAROLA_RE.sub(lambda m: (m[1] or m[3]) + (m[2] or m[4]) + "[secret]", text)
    text = ANAHTAR_RE.sub(lambda m: m[1] + m[2] + "[secret]", text)
    if EV_RE:
        text = EV_RE.sub("~", text)
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


ROUTE_LOG = SECRETS.parent / "yol.jsonl"


def yol_yaz(base_url, model, via=None):
    """Route log: which endpoint/model really answered (gateways put the upstream in X-Routed-Via).
    One short JSON line per answer; past ~200 KB only the newer half is kept."""
    try:
        r = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "url": base_url, "model": str(model)}
        if isinstance(via, str) and via:
            r["via"] = via[:120]
        ROUTE_LOG.parent.mkdir(parents=True, exist_ok=True)
        if ROUTE_LOG.exists() and ROUTE_LOG.stat().st_size > 200_000:
            lines = ROUTE_LOG.read_text(encoding="utf-8").splitlines()
            ROUTE_LOG.write_text("\n".join(lines[len(lines) // 2:]) + "\n", encoding="utf-8")
        with ROUTE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError:
        pass  # the log is never worth failing an answer


DUSUNCE_RE = re.compile(r"<think>.*?(?:</think>|$)", re.S)  # reasoning models (qwen3, deepseek-r1) put this in content


def istek(api, messages, model=None, timeout=60, max_tokens=None, deneme=3, kisisel=False, ek=None, ham=False):
    """One POST with retries. Returns (text, usage). 429/5xx/timeouts are retried with backoff (Retry-After honoured);
    on 429 the provider's fallback_model is tried first when configured. Untrusted providers only get redacted text,
    and none of the owner's profile/CV/notes (kisisel=True) when privacy.block_personal is on.
    ek: extra body fields (tools). ham=True returns (message dict, usage) so tool calls come back too."""
    pii = guvensiz(api)
    if pii and kisisel and C.get("privacy", {}).get("block_personal", True):
        raise PermissionError(f"{api['base_url']}: personal data is not sent to an untrusted provider")
    key = os.environ.get(api.get("key_env") or "", "")
    models = (model or api["model"]).split(",")  # "a,b": OpenRouter tries b when a is rate-limited
    govde = {"model": models[0], **({"models": models} if len(models) > 1 else {}),
             **({"max_tokens": max_tokens} if max_tokens else {}), **(ek or {}),
             "messages": [{**m, "content": redact(m["content"], pii)} if isinstance(m.get("content"), str) else m
                          for m in messages]}
    hata = None
    for i in range(deneme):
        req = urllib.request.Request(api["base_url"].rstrip("/") + "/chat/completions", json.dumps(govde).encode(), {
            "Content-Type": "application/json", "User-Agent": "pentarch/1.0",  # Groq 403s urllib's default agent
            **({"Authorization": f"Bearer {key}"} if key else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                j = json.loads(r.read())
                yol = r.headers.get("X-Routed-Via") if r.headers else None
            msg = j["choices"][0]["message"]
            text = DUSUNCE_RE.sub("", msg.get("content") or "").strip()
            if ham and (text or msg.get("tool_calls")):
                yol_yaz(api["base_url"], j.get("model") or govde["model"], yol)
                return {**msg, "content": text}, j.get("usage") or {}
            if not text:
                raise RuntimeError(f"{api['base_url']}: empty answer")
            yol_yaz(api["base_url"], j.get("model") or govde["model"], yol)
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


def mcp_diger(cli):
    """The same mcp_servers for gemini, codex and opencode: (extra codex flags, extra environment).
    codex: -c overrides; env_vars passes the named variables through (it gives MCP servers only PATH and the like).
    gemini: a settings file named by GEMINI_CLI_SYSTEM_SETTINGS_PATH (the top layer; it stands in for the machine's
    own system settings file during the run), env written as $NAME. opencode: OPENCODE_CONFIG, merged under the
    user's own config; its servers inherit opencode's environment. Values never go into a file."""
    servers = {ad: s for ad, s in (C.get("mcp_servers") or {}).items() if s.get("command")}
    if not servers:
        return [], {}
    if cli == "codex":
        ek = []
        for ad, s in servers.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]+", ad):
                continue  # only a bare TOML key fits the dotted override
            k = f"mcp_servers.{ad}"
            ek += ["-c", f"{k}.command={json.dumps(s['command'])}", "-c", f"{k}.args={json.dumps(list(s.get('args') or []))}"]
            if s.get("env"):
                ek += ["-c", f"{k}.env_vars={json.dumps(list(s['env']))}"]
        return ek, {}
    if cli == "gemini":
        veri = {"mcpServers": {ad: {"command": s["command"], "args": list(s.get("args") or []),
                                    **({"env": {v: "$" + v for v in s["env"]}} if s.get("env") else {})}
                               for ad, s in servers.items()}}
        f, degisken = SECRETS.parent / "gemini-mcp.json", "GEMINI_CLI_SYSTEM_SETTINGS_PATH"
    elif cli == "opencode":  # the v1 shape; opencode 2 still reads it
        veri = {"mcp": {ad: {"type": "local", "command": [s["command"], *(s.get("args") or [])], "enabled": True}
                        for ad, s in servers.items()}}
        f, degisken = SECRETS.parent / "opencode-mcp.json", "OPENCODE_CONFIG"
    else:
        return [], {}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(veri, indent=1), encoding="utf-8")
    return [], {degisken: str(f)}

