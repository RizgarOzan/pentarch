"""Pentarch setup: asks a few questions, writes the runtime home and adds the start-up shortcuts.

    python setup.py            interactive
    python setup.py --force    also overwrite the prompt/memory files already in the home folder

Re-running it is safe: answers default to what is already configured and your memory files are kept.
Nothing here leaves your computer; the Telegram token and API key go to <home>/secrets, never into the repo.
"""
import getpass
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Pentarch needs Python 3.10 or newer.")

REPO = Path(__file__).resolve().parent
APP = REPO / "app"
HOME = Path(os.environ.get("PENTARCH_HOME") or Path.home() / ".pentarch").expanduser()
CONFIG = HOME / "pentarch.json"
SECRETS = HOME / "secrets"
FORCE = "--force" in sys.argv
sys.stdout.reconfigure(errors="replace")  # old Windows code pages can't print every character
CLIS = ("claude", "gemini", "codex", "opencode")


TR = False


def t(tr, en):
    return tr if TR else en


def ask(q, default="", choices=None):
    hint = f" [{'/'.join(choices) if choices else default}]" if choices or default else ""
    while True:
        a = input(f"{q}{hint}: ").strip() or default
        if not choices or a in choices:
            return a
        print(t("  şunlardan biri: ", "  pick one of: ") + ", ".join(choices))


def yes(q, default=False):
    a = input(f"{q} [{t('E/h', 'Y/n') if default else t('e/H', 'y/N')}]: ").strip().lower()
    return default if not a else a in ("y", "yes", "e", "evet")


def secret(q):
    """Hidden input; falls back to plain input when stdin is piped (getpass reads the console on Windows)."""
    return getpass.getpass(q) if sys.stdin.isatty() else input(q)


def get_json(url, key=None, timeout=10):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# Chat API presets: name -> (base_url, suggested model, needs a key, where to get the key)
PRESETS = {
    "openrouter": ("https://openrouter.ai/api/v1", "google/gemma-4-31b-it:free", True, "https://openrouter.ai/keys"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", True, "https://console.groq.com/keys"),
    "ollama": ("http://localhost:11434/v1", "", False, ""),
    "lmstudio": ("http://localhost:1234/v1", "", False, ""),
}


def read_env(path):
    return dict(l.split("=", 1) for l in path.read_text(encoding="utf-8").splitlines() if "=" in l) if path.exists() else {}


def chat_api_setup(api):
    """Picks an endpoint, saves its key and checks it answers on /models. Returns the chat_api dict."""
    key_env = api.get("key_env", "PENTARCH_CHAT_KEY")
    print(t("\nUcuz tek seferlik işler için isteğe bağlı bir OpenAI uyumlu servis (sohbet ajanla devam eder).",
            "\nOptional OpenAI-compatible service for cheap one-shot work (the chat itself stays on the agent)."))
    cur = next((k for k, v in PRESETS.items() if v[0] == api.get("base_url")), "custom" if api.get("base_url") else "none")
    pick = ask(t("Servis", "Service"), cur, (*PRESETS, "custom", "none"))
    if pick == "none":
        return {"base_url": "", "model": "", "key_env": key_env}
    base, model, need_key, key_url = PRESETS.get(pick, (api.get("base_url", ""), api.get("model", ""), True, ""))
    if pick == "custom":
        base = ask("base_url (…/v1)", base)
    env_file = SECRETS / "keys.env"
    saved = read_env(env_file)
    key = os.environ.get(key_env) or saved.get(key_env, "")
    if need_key and (not key or yes(t("Kayıtlı API anahtarı değiştirilsin mi?", "Replace the saved API key?"))):
        if key_url:
            print(t(f"  Anahtarı buradan al: {key_url}", f"  Get a key here: {key_url}"))
        new = secret(t(f"API anahtarı (gizli, secrets/keys.env içine {key_env} olarak yazılır; boş geçer): ",
                       f"API key (hidden, saved to secrets/keys.env as {key_env}; empty skips): ")).strip()
        if new:
            key = saved[key_env] = new
            env_file.write_text("".join(f"{k}={v}\n" for k, v in saved.items()), encoding="utf-8")
    try:
        ids = [m.get("id") for m in get_json(base.rstrip("/") + "/models", key).get("data", [])]
        print(t(f"  Bağlantı tamam: {len(ids)} model görünüyor.", f"  Connected: {len(ids)} models visible."))
        if not model and ids:
            model = ids[0]
        if len(ids) <= 12:
            print("  " + ", ".join(ids))
    except Exception as e:
        ids = []
        print(t(f"  ! Bağlantı kurulamadı ({e}). Ayar yine de kaydedilir; servisi açıp kurulumu yeniden çalıştırabilirsin.",
                f"  ! Could not connect ({e}). The setting is saved anyway; start the service and run setup again."))
    model = ask("Model", api.get("model") if api.get("base_url") == base and api.get("model") else model)
    if ids and model not in ids:
        print(t("  ! Bu model listede yok, adını kontrol et.", "  ! That model is not in the list; check the name."))
    return {"base_url": base, "model": model, "key_env": key_env}


def telegram_setup():
    tok = SECRETS / "telegram.txt"
    if tok.exists() and not yes(t("Kayıtlı Telegram token'ı değiştirilsin mi?", "Replace the saved Telegram token?")):
        return
    print(t("\nTelegram: @BotFather'a yaz, /newbot gönder, verdiği token'ı kopyala.",
            "\nTelegram: talk to @BotFather, send /newbot, copy the token it gives."))
    while True:
        tk = secret(t("Bot token (gizli): ", "Bot token (hidden): ")).strip()
        if not tk:
            print(t("  Atlandı; sonra secrets/telegram.txt içine yazabilirsin.", "  Skipped; you can put it in secrets/telegram.txt later."))
            return
        try:
            bot = get_json(f"https://api.telegram.org/bot{tk}/getMe")["result"]
            print(t(f"  Token çalışıyor: @{bot['username']}", f"  Token works: @{bot['username']}"))
            break
        except urllib.error.HTTPError:
            print(t("  ! Telegram bu token'ı kabul etmedi.", "  ! Telegram did not accept that token."))
            if not yes(t("Yeniden denensin mi?", "Try again?"), True):
                return
        except Exception as e:  # offline or blocked: keep the token, it may still be right
            print(t(f"  ! Telegram'a ulaşılamadı ({type(e).__name__}); token denenmeden kaydediliyor.",
                    f"  ! Could not reach Telegram ({type(e).__name__}); saving the token unchecked."))
            break
    tok.write_text(tk + "\n", encoding="utf-8")


def agent_test(cli):
    """One tiny prompt through the agent CLI, so a missing login shows up now instead of on the first message."""
    q = "Reply with only the word: ok"
    args = {"claude": ["-p", q], "gemini": ["-p", q], "codex": ["exec", "--skip-git-repo-check", q], "opencode": ["run", q]}[cli]
    try:
        r = subprocess.run([shutil.which(cli) or cli, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180, cwd=HOME, env={**os.environ, "GEMINI_CLI_TRUST_WORKSPACE": "true"})
        ok = r.returncode == 0 and r.stdout.strip()
        last = ((r.stdout.strip() if ok else "") or r.stderr.strip() or r.stdout.strip()).splitlines()[-1:] or [""]
    except Exception as e:
        ok, last = False, [str(e)]
    if ok:
        print(t(f"  {cli} cevap verdi: {last[0][:60]}", f"  {cli} answered: {last[0][:60]}"))
    else:
        login = {"claude": "claude", "gemini": "gemini", "codex": "codex login", "opencode": "opencode auth login"}[cli]
        print(t(f"  ! {cli} cevap vermedi: {last[0][:160]}\n    Giriş yapmak için bir terminalde çalıştır: {login}",
                f"  ! {cli} did not answer: {last[0][:160]}\n    To log in, run in a terminal: {login}"))


def shortcut(path, args, icon):
    """Windows .lnk through WScript.Shell; pythonw so no console window stays open."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:P_LNK);$s.TargetPath=$env:P_EXE;"
          "$s.Arguments=$env:P_ARGS;$s.WorkingDirectory=$env:P_DIR;$s.IconLocation=$env:P_ICO;$s.Save()")
    env = {**os.environ, "P_LNK": str(path), "P_EXE": str(pyw if pyw.exists() else sys.executable),
           "P_ARGS": args, "P_DIR": str(APP), "P_ICO": str(icon)}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True)


def main():
    global TR
    old = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    agent = old.get("agent", {})
    print(f"Pentarch setup. Home folder: {HOME}\n")

    lang = ask("Language / Dil", old.get("lang", "en"), ("en", "tr"))
    TR = lang == "tr"
    owner = ask(t("Senin adın", "Your name"), old.get("owner", ""))
    name = ask(t("Asistanın adı", "Assistant name"), old.get("name", "Pentarch"))
    notes = ask(t("Not klasörü (markdown)", "Notes folder (markdown)"), old.get("notes_dir", "~/notes"))

    found = [c for c in CLIS if shutil.which(c)]
    print(t("Bulunan ajan CLI'ları: ", "Agent CLIs found: ") + (", ".join(found) or "-"))
    cli = ask(t("Ajan CLI", "Agent CLI"), agent.get("cli", found[0] if found else "claude"), CLIS)
    if not shutil.which(cli):
        print(t(f"  ! {cli} henüz PATH'te yok; Pentarch'ı başlatmadan önce kur ve giriş yap.",
                f"  ! {cli} is not on PATH yet; install it and log in before starting Pentarch."))
    elif yes(t(f"{cli} şimdi kısa bir mesajla denensin mi (giriş yapılmış mı diye)?",
               f"Send {cli} a short test message now (checks that it is logged in)?"), True):
        agent_test(cli)
    same = agent.get("cli") == cli
    models = {"claude": ("sonnet", "opus", "haiku")}.get(cli, ("", "", ""))
    if cli != "claude":
        print(t("  Model adlarını boş bırakırsan CLI'ın kendi varsayılanı kullanılır.",
                "  Leave the model names empty to use the CLI's own default."))
    fast = ask(t("Günlük model", "Everyday model"), agent.get("fast_model", models[0]) if same else models[0])
    deep = ask(t("Derin model", "Deep model"), agent.get("deep_model", models[1]) if same else models[1])
    light = ask(t("Hafif model", "Light model"), agent.get("light_model", models[2]) if same else models[2])
    print(t("İzin modu: acceptEdits = dosya düzenler, kabuk allowed_tools ile sınırlı (daha güvenli);\n"
            "           bypassPermissions = her şey serbest (zamanlanmış işlerin çoğu bunu ister).",
            "Permission mode: acceptEdits = edits files, shell limited to allowed_tools (safer);\n"
            "                 bypassPermissions = everything allowed (most scheduled jobs need it)."))
    perm = ask(t("İzin modu", "Permission mode"), agent.get("permission_mode", "acceptEdits"), ("acceptEdits", "bypassPermissions"))

    SECRETS.mkdir(parents=True, exist_ok=True)
    api = chat_api_setup(old.get("chat_api", {}))
    telegram_setup()

    off = set(old.get("jobs_off", ["insa", "posta"]))
    print(t("\nİki rutin ilk başta kapalı; istersen şimdi aç, sonra panelden de değiştirebilirsin (Ayarlar > Kapalı işler).",
            "\nTwo routines start off; turn them on now if you like, or later in the panel (Settings > Disabled routines)."))
    for job, tr_q, en_q in (("insa", "Gece kendini geliştirme turu (insa) açılsın mı?", "Turn on the nightly self-build round (insa)?"),
                            ("posta", "Posta kontrolü (posta) açılsın mı?", "Turn on the mail check (posta)?")):
        if yes(t(tr_q, en_q), job not in off):
            off.discard(job)
        else:
            off.add(job)

    cfg = {**old, "owner": owner or "Owner", "name": name or "Pentarch", "lang": lang, "notes_dir": notes,
           "agent": {**agent, "cli": cli, "fast_model": fast, "deep_model": deep, "light_model": light,
                     "permission_mode": perm},
           "chat_api": api, "jobs_off": sorted(off)}
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    panel_settings = HOME / "ayarlar.json"  # the panel's own switches, once Pentarch has run
    if panel_settings.exists():
        a = json.loads(panel_settings.read_text(encoding="utf-8"))
        a["kapali_isler"] = sorted(set(a.get("kapali_isler", [])) - {"insa", "posta"} | off)
        panel_settings.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(notes).expanduser().mkdir(parents=True, exist_ok=True)

    fill = {"{{APP}}": APP.as_posix(), "{{HOME}}": HOME.as_posix(), "{{NOTES}}": Path(notes).expanduser().as_posix(),
            "{{OWNER}}": cfg["owner"], "{{NAME}}": cfg["name"]}
    kept = []
    for src in sorted((REPO / "templates" / lang).iterdir()):
        dst = HOME / src.name
        if dst.exists() and not FORCE:
            kept.append(src.name)
            continue
        text = src.read_text(encoding="utf-8")
        for k, v in fill.items():
            text = text.replace(k, v)
        dst.write_text(text, encoding="utf-8")
    if kept:
        print(t(f"Olduğu gibi kaldı: {', '.join(kept)} (--force üstüne yazar)", f"Kept existing: {', '.join(kept)} (--force overwrites)"))
    (HOME / "v2.on").write_text("", encoding="utf-8") if cli == "claude" else (HOME / "v2.on").unlink(missing_ok=True)

    if yes(t("\nPython paketleri kurulsun mu (sesli mesaj ve sesli cevap)?", "\nInstall the Python packages (voice in/out)?"), True):
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REPO / "requirements.txt")])

    if os.name == "nt":
        icon = REPO / "assets" / "pentarch.ico"
        appdata = Path(os.environ["APPDATA"]) / "Microsoft/Windows"
        if yes(t("Windows açılınca Pentarch başlasın mı?", "Start Pentarch when Windows starts?"), True):
            shortcut(appdata / "Start Menu/Programs/Startup/Pentarch.lnk", f'-I "{APP / "pentarch.py"}" --quiet', icon)
        if yes(t("Masaüstüne panel kısayolu eklensin mi?", "Add a desktop shortcut for the panel?"), True):
            desk = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
            shortcut(desk / f"{cfg['name']}.lnk", f'-I "{APP / "pentarch.py"}" --panel', icon)

    print(t(f"""
Bitti. Başlatmak için:  python -I "{APP / 'pentarch.py'}"
Sonra Telegram'dan botuna herhangi bir mesaj at: ilk yazan sohbet sahip olur.
Ayarlar: {CONFIG}   Hafıza ve istemler: {HOME}""", f"""
Done. Start it with:  python -I "{APP / 'pentarch.py'}"
Then send any message to your bot from Telegram: the first chat that writes becomes the owner.
Settings: {CONFIG}   Memory and prompts: {HOME}"""))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit(t("\nİptal edildi.", "\nCancelled."))
