"""Pentarch configuration: one JSON file in the runtime home, merged over the defaults below.

Runtime home is ~/.pentarch (override with the PENTARCH_HOME environment variable). setup.py writes
pentarch.json there; edit it by hand or re-run setup. Secrets never live in this file: the Telegram token is
in <home>/secrets/telegram.txt and API keys are read from environment variables (or <home>/secrets/keys.env).
"""
import json
import os
from pathlib import Path

HOME = Path(os.environ.get("PENTARCH_HOME") or Path.home() / ".pentarch").expanduser()
CONFIG_FILE = HOME / "pentarch.json"
SECRETS = HOME / "secrets"

DEFAULTS = {
    "owner": "Owner",              # what the assistant calls you
    "name": "Pentarch",            # the assistant's name
    "lang": "en",                  # en | tr: language of replies and of the messages the code itself sends
    "notes_dir": "~/notes",        # any folder of markdown notes (Obsidian vault, wiki...); the agent works here
    "extra_dirs": [],              # more folders the agent may read/write (your code folder, for example)
    "github_user": "",             # for PR tracking; empty turns it off
    "agent": {
        "cli": "claude",           # claude | gemini | codex | opencode (claude has every feature; see README)
        "fast_model": "sonnet",    # everyday chat
        "deep_model": "opus",      # analysis/planning messages
        "light_model": "haiku",    # filters and short rewrites when no chat_api is set
        # headless runs cannot answer permission prompts. "acceptEdits" lets the agent edit files but blocks
        # shell commands outside allowed_tools; "bypassPermissions" allows everything (needed by most jobs).
        "permission_mode": "acceptEdits",
        "bypass_confirmed": False,  # setup sets it after a second yes; only then codex/gemini run without sandbox
        # helpers for parallel subtasks (alt.py): e.g. ["gemini", "codex"]. The main agent hands them work and
        # checks what comes back; empty = subtasks run on the main CLI too.
        "workers": [],
        "max_parallel": 8,         # subtasks running at once (alt.py)
        "allowed_tools": ["Read", "Grep", "Glob", "WebSearch", "WebFetch", "Bash(python *)", "Bash(gh pr view *)", "Bash(gh pr list *)", "Bash(gh pr diff *)",
                          "Bash(gh issue view *)", "Bash(gh issue list *)", "Bash(gh repo view *)", "Bash(gh api *)"],
    },
    # optional OpenAI-compatible endpoint for cheap one-shot work (filters, shortening, council seats).
    # key_env names the environment variable that holds the key; nothing is stored here.
    "chat_api": {"base_url": "", "model": "", "key_env": "PENTARCH_CHAT_KEY"},
    # ordered list of the same shape, tried one after another: {base_url, model, key_env, fallback_model?,
    # trusted? | free? | trains_on_data?}. Empty = the single chat_api above.
    "providers": [],
    # default_deny: providers not marked "trusted" count as untrusted. Untrusted ones (and every free/trains_on_data
    # one) get e-mails, phones, IBAN/card numbers masked; block_personal keeps profile/CV/notes away from them.
    "privacy": {"default_deny": True, "block_personal": True},
    "council_timeout": 900,        # seconds for a whole council; late seats are dropped
    # council ("konsey: question" in Telegram): each seat is the agent CLI or an OpenAI-compatible endpoint
    "council": [],
    "notify_apps": {},             # Windows notification app id -> label to watch; empty turns watching off
    "auto_reply": False,           # may the agent answer notifications/messages on your behalf
    "desktop_control": False,      # Windows-MCP desktop control for the chat brain
    "voice_replies": True,         # answer voice with voice (edge-tts, needs internet)
    "tts_voice": "",               # edge-tts voice name; empty picks one for lang
    "whisper": {"model": "small", "language": ""},  # faster-whisper; empty language = auto-detect
    "health_urls": [],             # extra sites to watch on the panel (internet and agent login are always checked)
    "net_quota_gb": 0,             # monthly data cap; 0 = no metered-connection mode
    "jobs_off": ["insa", "posta"], # routines off at first start (JOBS in pentarch.py); panel Settings turns them on
    # learning loop (ogren.py): after a chat turn a cheap model proposes notes/skill patches; the owner approves each
    "learning": {"enabled": False, "max_pending": 20},
    "memory": {"inject_max_chars": 8000},  # cap for the core memory a new session gets (profile + memory.md)
    # shell work backend (kum.py): local | docker. docker missing = command refused, never run on the host instead
    "sandbox": {"backend": "local", "image": "python:3.12-slim", "network": False},
    # MCP servers handed to Claude Code: name -> {"command", "args": [], "env": ["VAR_NAME"]}. env lists names only;
    # the value stays in the environment (written as ${VAR_NAME}, Claude Code expands it)
    "mcp_servers": {},
    # extra gateways, off by default; same commands as Telegram. Passwords/tokens come from the named env variables
    "gateways": {
        "email": {"enabled": False, "imap_host": "", "smtp_host": "", "smtp_port": 465, "user": "",
                  "password_env": "PENTARCH_MAIL_PASSWORD", "allowed_from": [], "every": 120},
        "discord": {"enabled": False, "token_env": "PENTARCH_DISCORD_TOKEN", "channel_id": "", "owner_id": "", "every": 15},
    },
    "panel_port": 47824,


    "lock_port": 47823,
}


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load():
    if CONFIG_FILE.exists():
        try:
            return _merge(DEFAULTS, json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except ValueError as e:
            raise SystemExit(f"{CONFIG_FILE} is not valid JSON: {e}")
    return dict(DEFAULTS)


def load_keys():
    """KEY=value lines from secrets/keys.env go into the environment unless already set."""
    f = SECRETS / "keys.env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


C = load()
load_keys()
OWNER, NAME, LANG = C["owner"], C["name"], C["lang"]
NOTES = Path(C["notes_dir"]).expanduser()
EXTRA_DIRS = [Path(d).expanduser() for d in C["extra_dirs"]]
LANG_NAME = {"tr": "Turkish", "en": "English"}.get(LANG, "English")


def allowed_tools(tools):
    """`Bash(python *)` (also in older configs) becomes Pentarch's own scripts only; `python -c ...` is not allowed."""
    app = Path(__file__).resolve().parent.as_posix()
    own = f'Bash(python -I "{app}/*)'
    return ",".join(own if t == "Bash(python *)" else "Bash(gh pr view *)" if t == "Bash(gh *)" else t for t in tools)


def T(tr, en):
    """User-facing text in the configured language."""
    return tr if LANG == "tr" else en
