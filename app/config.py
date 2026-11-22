"""Pentarch configuration: one JSON file in the runtime home, merged over the defaults below.

Runtime home is ~/.pentarch (override with the PENTARCH_HOME environment variable). setup.py writes
pentarch.json there; edit it by hand or re-run setup. Secrets never live in this file: the Telegram token is
in <home>/secrets/telegram.txt and API keys are read from environment variables (or <home>/secrets/keys.env).
"""
import json
import os
from pathlib import Path

VERSION = "1.0.0"
HOME = Path(os.environ.get("PENTARCH_HOME") or Path.home() / ".pentarch").expanduser()
CONFIG_FILE = HOME / "pentarch.json"
SECRETS = HOME / "secrets"


def _extend_path():
    """launchd/systemd keep the PATH setup saw. A CLI installed or moved later (brew, npm -g, pipx, bun) would then
    vanish, so the usual user bin folders are appended when they exist. Runs before anything calls shutil.which."""
    if os.name == "nt":
        return
    have = os.environ.get("PATH", "").split(os.pathsep)
    h = Path.home()
    extra = [str(p) for p in (h / ".local/bin", h / ".npm-global/bin", h / ".bun/bin", h / ".volta/bin",
                              h / ".cargo/bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin"))
             if str(p) not in have and p.is_dir()]
    if extra:
        os.environ["PATH"] = os.pathsep.join([*have, *extra])


_extend_path()

DEFAULTS = {
    "owner": "Owner",              # what the assistant calls you
    "name": "Pentarch",            # the assistant's name
    "lang": "en",                  # en | tr: language of replies and of the messages the code itself sends
    "reply_lang": "",              # any other language for the agent's replies ("Español"); code messages stay in `lang`
    "notes_dir": "~/notes",        # any folder of markdown notes (Obsidian vault, wiki...); the agent works here
    "extra_dirs": [],              # more folders the agent may read/write (your code folder, for example)
    "github_user": "",             # for PR tracking; empty turns it off
    "plan": "max",                 # pro | max | api: "pro" makes scheduled runs lean and sparse (README, Using with Pro)
    "agent": {
        "cli": "claude",           # claude | gemini | codex | opencode | api (no CLI: providers, see api_ajan.py; claude has every feature)
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
                          "Bash(gh issue view *)", "Bash(gh issue list *)", "Bash(gh repo view *)"],
    },
    "menajer": {"max_per_day": 4, "min_cv_score": 75},  # morning application packages (menajer.py); sends nothing by itself
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
    # faster-whisper; empty language = auto-detect. groq_key_env names an env var with a Groq key: voice then goes to
    # Groq's hosted whisper first (audio leaves the machine) and falls back to local whisper. Empty = local only.
    "whisper": {"model": "small", "language": "", "groq_key_env": ""},
    "health_urls": [],             # extra sites to watch on the panel (internet and agent login are always checked)
    "net_quota_gb": 0,             # monthly data cap; 0 = no metered-connection mode
    "jobs_off": ["guncelle", "insa", "posta"], # routines off at first start (JOBS in pentarch.py); panel Settings turns them on
    # learning loop (ogren.py): after a chat turn a cheap model proposes notes/skill patches; the owner approves each
    "learning": {"enabled": False, "max_pending": 20},
    # tiered routing for ledger jobs (sirket.py): cheap -> mid -> top with a deep-model review; off = one run as before
    "routing": {"enabled": False},
    # nightly self-improvement (gelisim.py): proposes fixes as Yes/No; code changes only ever become a .patch file
    "self_improve": {"enabled": False},
    "memory": {"inject_max_chars": 8000},  # cap for the core memory a new session gets (profile + memory.md)
    # shell work backend (kum.py): local | docker. docker missing = command refused, never run on the host instead
    "sandbox": {"backend": "local", "image": "python:3.12-slim", "network": False},  # backend: local | docker | ssh (+ "host", "dir")
    # MCP servers handed to the agent CLI (claude, gemini, codex, opencode): name ->{"command", "args": [], "env": ["VAR_NAME"]}. env lists names only;
    # the value stays in the environment (written as ${VAR_NAME}, Claude Code expands it)
    "mcp_servers": {},
    # extra gateways, off by default; same commands as Telegram. Passwords/tokens come from the named env variables
    "gateways": {
        "email": {"enabled": False, "imap_host": "", "smtp_host": "", "smtp_port": 465, "user": "",
                  "password_env": "PENTARCH_MAIL_PASSWORD", "allowed_from": [], "auth_server": "", "every": 120},
        "discord": {"enabled": False, "token_env": "PENTARCH_DISCORD_TOKEN", "channel_id": "", "owner_id": "", "every": 15},
        # Slack: bot token (xoxb-) with channels:history or im:history, and chat:write. New apps outside the Slack
        # Marketplace may read history once a minute, hence every 60
        "slack": {"enabled": False, "token_env": "PENTARCH_SLACK_TOKEN", "channel_id": "", "owner_id": "", "every": 60},
        # Signal through signal-cli: account is the number registered to signal-cli, owner is your own number
        "signal": {"enabled": False, "cli": "signal-cli", "account": "", "owner": "", "every": 15},
    },
    "panel_port": 47824,
    "chat_daily_usd": 0,           # daily cap for Telegram chat spend; once reached no AGIR hand-off. 0 = no cap
    # pre-send reply audit (denetim.py): stale dates add a warning line, unsourced numbers are only logged.
    # summary_fields {name: regex} must all show up in a long reply whose source matches summary_trigger; {} = off
    "audit": {"enabled": True, "summary_trigger": "", "summary_fields": {}},
    # shadow mode: small jobs (shorten/triage) also go to a candidate endpoint in the background; both answers are
    # logged to <home>/golge.jsonl so you can see whether a cheaper model would do. Nothing user-facing changes.
    # Endpoint fields have the providers shape; empty base_url = the last entry of providers
    "shadow": {"enabled": False, "base_url": "", "model": "", "key_env": ""},
    # push-to-talk (Windows): hold the key, speak, release; the voice and a screenshot go to the chat as a message.
    # hotkey_vk is a Windows virtual-key code (0x78 = F9); mic is the dshow device name ffmpeg sees ("" = off)
    "push_to_talk": {"enabled": False, "hotkey_vk": 0x78, "mic": "", "min_hold": 0.4},
    # live meeting assistant (`pentarch.py meeting`): goal is what you want out of the call (or <home>/gorusme.md)
    "meeting": {"goal": "", "port": 8765, "mic": True},
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


def agent_env(**extra):
    """The environment for an agent CLI run, without Pentarch's own secrets (Telegram token, mail password, Discord
    token): the agent never needs them, and under bypassPermissions a plain `env` would print them. Model and MCP keys
    stay, since the CLI and its MCP servers read them."""
    g = C.get("gateways", {})
    own = {"PENTARCH_TELEGRAM_TOKEN", "PENTARCH_ICAL", g.get("email", {}).get("password_env"), g.get("discord", {}).get("token_env"),
           g.get("slack", {}).get("token_env")}
    return {**{k: v for k, v in os.environ.items() if k not in own}, **extra}


C = load()
load_keys()
OWNER, NAME, LANG = C["owner"], C["name"], C["lang"]
NOTES = Path(os.environ.get("PENTARCH_NOTES_DIR") or C["notes_dir"]).expanduser()  # the env var lets a test or a second setup use another folder
EXTRA_DIRS = [Path(d).expanduser() for d in C["extra_dirs"]]
# reply_lang names a language in words ("Deutsch"); this is its two-letter code where a CV or a voice needs one
LANG_CODES = {"deutsch": "de", "german": "de", "español": "es", "espanol": "es", "spanish": "es", "français": "fr", "francais": "fr", "french": "fr"}
LANG_NAME = (C.get("reply_lang") or "").strip() or {"tr": "Turkish", "en": "English"}.get(LANG, "English")


def allowed_tools(tools):
    """`Bash(python *)` (also in older configs) becomes Pentarch's own scripts only; `python -c ...` is not allowed."""
    app = Path(__file__).resolve().parent.as_posix()
    own = f'Bash(python -I "{app}/*)'
    return ",".join(own if t == "Bash(python *)" else "Bash(gh pr view *)" if t == "Bash(gh *)" else t for t in tools)


def denied_tools():
    """Keys and the pairing code live in SECRETS; a prompt-injected page must not be able to make the agent read them.
    Read is a hard block; the Bash rule only catches commands that spell the folder out (a speed bump, not a wall).
    Only Claude Code takes deny rules; the other CLIs have no equivalent (README, security)."""
    p = SECRETS.resolve().as_posix()
    home = Path.home().resolve().as_posix()
    rule = f"~{p[len(home):]}" if p.startswith(home + "/") else f"/{p}"  # `//abs/path` form for paths outside ~
    return f"Read({rule}/**),Read({rule}),Bash(*{SECRETS.parent.name}/{SECRETS.name}*),Bash(*keys.env*),Bash(*telegram.txt*)"


def T(tr, en):
    """User-facing text in the configured language."""
    return tr if LANG == "tr" else en
