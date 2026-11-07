"""Council seats: add, list, test and remove them without editing pentarch.json by hand.

    python -I koltuk.py list
    python -I koltuk.py add ENVOY --preset openrouter --model google/gemma-4-31b-it:free [--role "..."]
    python -I koltuk.py add LOCAL --preset ollama --model llama3.2
    python -I koltuk.py add DEEP --agent --model opus              # a seat on the agent CLI itself
    python -I koltuk.py add X --preset custom --base-url https://host/v1 --model m --key-env MY_KEY
    python -I koltuk.py key OPENROUTER_API_KEY                      # store a key (hidden prompt, or piped on stdin)
    python -I koltuk.py test ENVOY                                  # one short question to that seat
    python -I koltuk.py remove ENVOY

Keys never go on the command line: `add` asks for a missing key with a hidden prompt (or reads it from stdin
when piped) and writes it to <home>/secrets/keys.env. The seat itself (name, kind, base_url, model, key_env,
role) goes into the "council" list of pentarch.json. OpenRouter accepts "model-a,model-b": the next one is
tried when the first is rate-limited.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, CONFIG_FILE, SECRETS, T  # noqa: E402

# preset -> (base_url, default key env, default model, where to get a key); "" key env = no key needed
PRESETS = {
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "google/gemma-4-31b-it:free", "https://openrouter.ai/keys"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile", "https://console.groq.com/keys"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "nvidia/nemotron-3-ultra-550b-a55b", "https://build.nvidia.com"),
    # local FreeLLMAPI router (github.com/tashfeenahmed/freellmapi): auto:* models fall over to whichever provider is up
    "freellmapi": ("http://127.0.0.1:31415/v1", "FREELLMAPI_KEY", "auto:magi-usta", ""),
    "ollama": ("http://localhost:11434/v1", "", "", ""),
    "lmstudio": ("http://localhost:1234/v1", "", "", ""),
}
KEYS_FILE = SECRETS / "keys.env"


def read_keys():
    if not KEYS_FILE.exists():
        return {}
    return dict(l.split("=", 1) for l in KEYS_FILE.read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))


def save_key(env, value):
    """Writes KEY=value into secrets/keys.env (0600 where the OS supports it) and into this process's environment."""
    keys = read_keys()
    keys[env] = value.strip()
    SECRETS.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text("".join(f"{k}={v}\n" for k, v in keys.items()), encoding="utf-8")
    try:
        os.chmod(KEYS_FILE, 0o600)
    except OSError:
        pass
    os.environ[env] = keys[env]


def ask_key(env, key_url=""):
    if key_url:
        print(T(f"  Anahtarı buradan al: {key_url}", f"  Get a key here: {key_url}"))
    q = T(f"{env} (gizli, secrets/keys.env içine yazılır; boş geçer): ", f"{env} (hidden, saved to secrets/keys.env; empty skips): ")
    return (getpass.getpass(q) if sys.stdin.isatty() else sys.stdin.readline()).strip()


def has_key(env):
    return bool(env and (os.environ.get(env) or read_keys().get(env)))


def load_cfg():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}


def save_cfg(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def models(base_url, env):
    """Model ids the endpoint lists on /models; [] when it does not answer."""
    key = os.environ.get(env or "", "") or read_keys().get(env or "", "")
    req = urllib.request.Request(base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return [m.get("id") for m in json.load(r).get("data", [])]
    except Exception:
        return []


def add(name, preset=None, model="", base_url="", key_env=None, role="", agent=False, check=True):
    """Builds the seat, asks for a missing key, checks the model name and saves. Returns the seat dict."""
    name = name.strip().upper()
    if agent:
        seat = {"name": name, "kind": "agent", "model": model or C["agent"]["deep_model"]}
    else:
        if preset in PRESETS:
            base, env, default_model, key_url = PRESETS[preset]
        else:
            base, env, default_model, key_url = base_url, key_env or f"PENTARCH_{name}_KEY", model, ""
        if not base:
            raise SystemExit(T("base_url gerekli (…/v1)", "base_url is needed (…/v1)"))
        env = key_env if key_env is not None else env
        seat = {"name": name, "kind": "openai", "base_url": base, "model": model or default_model, "key_env": env}
        if env and not has_key(env):
            new = ask_key(env, key_url)
            if new:
                save_key(env, new)
        if check:
            ids = models(base, env)
            if not ids:
                print(T("  ! /models cevap vermedi (anahtar eksik ya da servis kapalı olabilir); yine de kaydedildi.",
                        "  ! /models did not answer (missing key or service down?); saved anyway."))
            elif not seat["model"]:
                seat["model"] = ids[0]
            elif seat["model"].split(",")[0] not in ids:
                print(T(f"  ! {seat['model']} bu uçta listelenmiyor; yine de kaydedildi.",
                        f"  ! {seat['model']} is not listed by this endpoint; saved anyway."))
            if env:  # /models is public on some services (OpenRouter), so a wrong key passes this check
                print(T(f"  anahtarı asıl sınayan: python app/koltuk.py test {name}", f"  the key itself is only verified by: python app/koltuk.py test {name}"))
    if role:
        seat["role"] = role
    cfg = load_cfg()
    council = [s for s in cfg.get("council", []) if (s.get("name") or "").upper() != name]
    cfg["council"] = council + [seat]
    save_cfg(cfg)
    return seat


def remove(name):
    cfg = load_cfg()
    before = cfg.get("council", [])
    cfg["council"] = [s for s in before if (s.get("name") or "").upper() != name.strip().upper()]
    save_cfg(cfg)
    return len(before) - len(cfg["council"])


def seats():
    return load_cfg().get("council", [])


def test(name):
    import magi  # noqa: E402  (imported late so list/add work without an agent CLI on PATH)
    seat = next((s for s in seats() if (s.get("name") or "").upper() == name.strip().upper()), None)
    if not seat:
        raise SystemExit(T(f"{name} diye bir koltuk yok", f"no seat named {name}"))
    q = T("Tek kelimeyle cevap ver: hazır mısın?", "Answer in one word: are you ready?")
    if seat.get("kind") == "openai":
        return magi.api_sor(seat, "", q, max_tokens=50)
    return magi.agent_sor(seat.get("model") or C["agent"]["deep_model"], "", q, timeout=120)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    a = sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("--preset", choices=(*PRESETS, "custom"))
    a.add_argument("--agent", action="store_true", help="a seat on the configured agent CLI")
    a.add_argument("--model", default="")
    a.add_argument("--base-url", default="")
    a.add_argument("--key-env")
    a.add_argument("--role", default="")
    a.add_argument("--no-check", action="store_true")
    sub.add_parser("remove").add_argument("name")
    sub.add_parser("test").add_argument("name")
    sub.add_parser("key").add_argument("env")
    args = p.parse_args(argv)
    if args.cmd == "list":
        for s in seats():
            print(f"{s.get('name')}: {s.get('kind', 'agent')} {s.get('model', '')} {s.get('base_url', '')}".rstrip())
        if not seats():
            print(T("Koltuk yok; konsey tek ajan koltuğuyla toplanır.", "No seats; the council meets as one agent seat."))
    elif args.cmd == "add":
        if not args.agent and not args.preset:
            p.error("--preset or --agent")
        s = add(args.name, args.preset, args.model, args.base_url, args.key_env, args.role, args.agent, not args.no_check)
        print(T(f"Eklendi: {s['name']} ({s['kind']}, {s['model']})", f"Added: {s['name']} ({s['kind']}, {s['model']})"))
    elif args.cmd == "remove":
        n = remove(args.name)
        print(T(f"Silinen: {n}", f"Removed: {n}"))
    elif args.cmd == "test":
        try:
            print(test(args.name))
        except Exception as e:  # 401, connection refused, missing CLI: one line, not a traceback
            raise SystemExit(T(f"{args.name} cevap vermedi: {e}", f"{args.name} did not answer: {e}"))
    elif args.cmd == "key":
        v = ask_key(args.env)
        if v:
            save_key(args.env, v)
            print(T(f"{args.env} kaydedildi.", f"{args.env} saved."))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
