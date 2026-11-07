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

TERMUX = "TERMUX_VERSION" in os.environ  # Android phone without a computer (Termux app)

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


sys.path.insert(0, str(APP))
import koltuk  # noqa: E402  (presets and the council-seat helpers; config.py resolves the same HOME)
PRESETS = koltuk.PRESETS  # name -> (base_url, key env, suggested model, where to get the key)
KEY_STEPS = {  # free tiers, no card needed; (tr, en) per step
    "openrouter": (("Google ya da GitHub ile giriş yap.", "Sign in with Google or GitHub."),
                   ("Keys > Create key; adı önemsiz, limit boş kalabilir.", "Keys > Create key; any name, leave the limit empty."),
                   ("Ücretsiz modellerin adı ':free' ile biter. 404 alırsan Settings > Privacy'den ücretsiz model kullanımını aç.",
                    "Free models end in ':free'. If you get 404, enable free-model use under Settings > Privacy.")),
    "groq": (("E-posta ya da GitHub ile giriş yap.", "Sign in with email or GitHub."),
             ("API Keys > Create API Key, anahtarı hemen kopyala (bir daha gösterilmez).",
              "API Keys > Create API Key and copy it now (it is shown once)."),
             ("Ücretsiz katman dakikada ~30 istek; günlük işler için yeter.", "The free tier allows ~30 requests a minute, enough for daily jobs.")),
    "nvidia": (("Giriş yap, bir model sayfası aç.", "Sign in and open any model page."),
               ("'Get API Key' düğmesi anahtarı verir; nvapi- ile başlar.", "'Get API Key' gives the key; it starts with nvapi-."),
               ("Ücretsiz kredi hesapla gelir, kart istemez.", "Free credits come with the account, no card.")),
    "ollama": (("ollama.com'dan kur, sonra: ollama pull gemma3", "Install from ollama.com, then: ollama pull gemma3"),
               ("Çalışırken http://localhost:11434 cevap verir; anahtar gerekmez.", "While it runs, http://localhost:11434 answers; no key needed.")),
    "lmstudio": (("lmstudio.ai'dan kur, bir model indir, Developer > Start Server.", "Install from lmstudio.ai, download a model, Developer > Start Server."),
                 ("Sunucu http://localhost:1234 üstünde; anahtar gerekmez.", "The server is on http://localhost:1234; no key needed.")),
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
    base, preset_env, model, key_url = PRESETS.get(pick, (api.get("base_url", ""), key_env, api.get("model", ""), ""))
    need_key = bool(preset_env)
    if pick == "custom":
        base = ask("base_url (…/v1)", base)
    env_file = SECRETS / "keys.env"
    saved = read_env(env_file)
    key = os.environ.get(key_env) or saved.get(key_env, "")
    if need_key and (not key or yes(t("Kayıtlı API anahtarı değiştirilsin mi?", "Replace the saved API key?"))):
        if key_url:
            print(t(f"  Anahtarı buradan al: {key_url}", f"  Get a key here: {key_url}"))
            for i, step in enumerate(KEY_STEPS.get(pick, ()), 1):
                print(f"    {i}. {t(*step)}")
        new = secret(t(f"API anahtarı (gizli, secrets/keys.env içine {key_env} olarak yazılır; boş geçer): ",
                       f"API key (hidden, saved to secrets/keys.env as {key_env}; empty skips): ")).strip()
        if new:
            key = saved[key_env] = new
            env_file.write_text("".join(f"{k}={v}\n" for k, v in saved.items()), encoding="utf-8")
            env_file.chmod(0o600)
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


def council_setup():
    """Optional council seats (MAGI): each one an OpenAI-compatible endpoint or the agent CLI. Later: koltuk.py."""
    have = [s.get("name") for s in koltuk.seats()]
    print(t(f"\nKonsey koltukları (konsey: soru): {', '.join(have) or 'yok, tek ajan koltuğu'}. Sonradan: python -I app/koltuk.py add ...",
            f"\nCouncil seats (council: question): {', '.join(have) or 'none, one agent seat'}. Later: python -I app/koltuk.py add ..."))
    while yes(t("Koltuk eklensin mi?", "Add a seat?"), not have):
        name = ask(t("Koltuk adı", "Seat name"), "ENVOY").upper()
        pick = ask(t("Servis", "Service"), "openrouter", (*PRESETS, "custom", "agent"))
        role = ask(t("Rolü (boş olabilir)", "Its role (may be empty)"), "")
        if pick == "agent":
            s = koltuk.add(name, agent=True, model=ask("Model", ""), role=role)
        elif pick == "custom":
            s = koltuk.add(name, "custom", ask("Model", ""), ask("base_url (…/v1)", ""), ask("key env", f"PENTARCH_{name}_KEY"), role)
        else:
            s = koltuk.add(name, pick, ask("Model", PRESETS[pick][2]), role=role)
        have.append(s["name"])
        print(t(f"  Eklendi: {s['name']} ({s['model']})", f"  Added: {s['name']} ({s['model']})"))


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
    tok.chmod(0o600)
    pair = SECRETS / "telegram-pair.txt"
    if not pair.exists():
        import secrets as _s
        pair.write_text(_s.token_hex(4), encoding="utf-8")
        pair.chmod(0o600)
    code = pair.read_text(encoding="utf-8").strip()
    print(t(f"  Bota Telegram'dan şunu yaz: /start {code}  (bu kodu bilmeyen bota sahip olamaz)",
            f"  In Telegram, send the bot: /start {code}  (without this code nobody else can claim it)"))


def agent_test(cli):
    """One tiny prompt through the agent CLI, so a missing login shows up now instead of on the first message."""
    q = "Reply with only the word: ok"
    args = {"claude": ["-p", q], "gemini": ["-p", q], "codex": ["exec", "--skip-git-repo-check", q], "opencode": ["run", q]}[cli]
    try:
        r = subprocess.run([shutil.which(cli) or cli, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90, cwd=HOME, stdin=subprocess.DEVNULL, env={**os.environ, "GEMINI_CLI_TRUST_WORKSPACE": "true"})
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


LEVELS = {  # answer -> (seniority words scan.py needs in a title, max years a posting may ask for, job_boards titles filter, title words to drop)
    "entry": (["intern", "junior", "entry level"], 2, ["intern", "internship", "junior", "graduate", "new grad", "entry", "trainee"], None),
    "mid": ([], 5, [], ["lead", "head", "principal", "staff", "director", "manager", "chief"]),
    "any": ([], 99, [], []),
}


def csv(q, default):
    return [x.strip() for x in ask(q, ", ".join(default)).split(",") if x.strip()]


def career_setup(old_cfg, lang):
    """Target roles, level, places, skills and job boards, once: tracker/profile.json for the scan and the agent,
    job_boards in pentarch.json for the watch routine. Re-runs default to the saved answers. Returns job_boards."""
    tracker = REPO / "tracker"
    pf = tracker / "profile.json"
    cur = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    boards_old = old_cfg.get("job_boards") or {}
    print(t("\nKariyer: ilan taraması, başvuru panosu ve asistanın iş hükümleri bu cevaplara göre çalışır (sonra: tracker/profile.json).",
            "\nCareer: the job scan, the application board and the assistant's verdicts on postings follow these answers (later: tracker/profile.json)."))
    if not yes(t("Kariyer takibi kurulsun mu?", "Set up the career tracker?"), True):
        return boards_old
    roles = csv(t("Hedef roller (virgülle)", "Target roles (comma separated)"), cur.get("target_roles") or ["junior software engineer"])
    cur_level = "entry" if cur.get("seniority") else "mid" if cur and int(cur.get("max_years", 2)) <= 5 else "any" if cur else "entry"
    level = ask(t("Seviye", "Level"), cur_level, tuple(LEVELS))
    locs = csv(t("Yerler (remote, şehir, ülke)", "Places (remote, city, country)"), cur.get("locations") or ["remote"])
    skills = csv(t("Becerilerin (virgülle)", "Your skills (comma separated)"), cur.get("skills") or [])
    cb = cur.get("boards") or {}
    print(t("  İzlenecek şirket panoları; slug, kariyer sayfasının adresindeki son parça (boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>). Boş olabilir.",
            "  Company boards to watch; the slug is the last part of the careers URL (boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>). May be empty."))
    boards = {k: csv(f"  {k}", cb.get(k) or boards_old.get(k) or []) for k in ("greenhouse", "lever", "ashby")}
    seniority, years, titles, exclude = LEVELS[level]
    sys.path.insert(0, str(tracker))
    import build  # noqa: E402
    build.init(tracker)
    prof = json.loads(pf.read_text(encoding="utf-8"))
    prof.pop("_", None)  # the example's "copy me" note
    prof.update(target_roles=roles, seniority=seniority, locations=locs, skills=skills, max_years=years,
                boards={**(prof.get("boards") or {}), **boards})
    if exclude is not None:  # the example's exclude list is for entry level
        prof["exclude"] = exclude
    prof.setdefault("cv", {})["language"] = lang
    pf.write_text(json.dumps(prof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(t(f"  Yazıldı: {pf}. İlanları taramak için: python -I tracker/scan.py --config tracker/config.json",
            f"  Written: {pf}. To scan the boards: python -I tracker/scan.py --config tracker/config.json"))
    return {**boards_old, "greenhouse": boards["greenhouse"], "lever": boards["lever"], "titles": titles, "fields": [],
            "locations": [l for l in locs if not l.lower().startswith("relocation")]}


def skills_setup(cli):
    """Repo skills (skills/<name>/SKILL.md): a pointer in <home>/beceriler so memory search attaches them, and for
    Claude Code a copy under ~/.claude/skills so /<name> works in the chat too."""
    dirs = sorted(d for d in (REPO / "skills").iterdir() if (d / "SKILL.md").exists())
    if not dirs:
        return
    pointers = HOME / "beceriler"
    pointers.mkdir(exist_ok=True)
    for d in dirs:
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        head = text.split("---")[1] if text.startswith("---") else ""
        desc = next((l.split(":", 1)[1].strip() for l in head.splitlines() if l.startswith("description:")), d.name)
        (pointers / f"{d.name}.md").write_text(f"When: {desc}\nRead and follow {d / 'SKILL.md'}\n", encoding="utf-8")
    names = ", ".join(d.name for d in dirs)
    if cli == "claude" and yes(t(f"Beceriler Claude Code'a da kopyalansın mı ({names})?", f"Copy the skills into Claude Code too ({names})?"), True):
        target = Path.home() / ".claude" / "skills"
        for d in dirs:
            shutil.copytree(d, target / d.name, dirs_exist_ok=True)
            sk = target / d.name / "SKILL.md"  # the copy runs from any folder, so name the tool by its full path
            sk.write_text(sk.read_text(encoding="utf-8").replace("skills/linkedin/li.py", f'"{REPO / "skills" / "linkedin" / "li.py"}"').replace("skills/cv/cv.py", f'"{REPO / "skills" / "cv" / "cv.py"}"'), encoding="utf-8")
        print(t(f"  Kopyalandı: {target}", f"  Copied to: {target}"))
    elif cli != "claude":
        print(t(f"  Beceriler {REPO / 'skills'} altında; {cli} için kendi beceri klasörüne kopyalayabilirsin.",
                f"  Skills live in {REPO / 'skills'}; copy them into {cli}'s own skills folder if it has one."))


def mcp_setup(old):
    """MCP servers handed to Claude Code (config mcp_servers). Env variables are asked by name only, never by value."""
    servers = dict(old.get("mcp_servers") or {})
    if servers:
        print(t("  Kayıtlı MCP sunucuları: ", "  MCP servers on file: ") + ", ".join(servers))
    while yes(t("MCP sunucusu eklensin mi?", "Add an MCP server?"), False):
        name = ask(t("  Ad", "  Name"))
        command = ask(t("  Komut (ör. npx)", "  Command (e.g. npx)"))
        if not name or not command:
            break
        args = ask(t("  Argümanlar (boşlukla)", "  Arguments (space separated)")).split()
        env = [v for v in csv(t("  Gereken ortam değişkeni ADLARI (virgülle, değer değil)",
                                "  Environment variable NAMES it needs (comma separated, not values)"), []) if v]
        servers[name] = {"command": command, "args": args, **({"env": env} if env else {})}
    return servers


def shortcut(path, args, icon):
    """Windows .lnk through WScript.Shell; pythonw so no console window stays open."""
    pyw = Path(sys.executable).with_name("pythonw.exe")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:P_LNK);$s.TargetPath=$env:P_EXE;"
          "$s.Arguments=$env:P_ARGS;$s.WorkingDirectory=$env:P_DIR;$s.IconLocation=$env:P_ICO;$s.Save()")
    env = {**os.environ, "P_LNK": str(path), "P_EXE": str(pyw if pyw.exists() else sys.executable),
           "P_ARGS": args, "P_DIR": str(APP), "P_ICO": str(icon)}
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True)


def wiki_backup(notes):
    """Optional: the notes folder becomes a git repo pushed to a private repo the owner made; the nightly round pushes."""
    if not shutil.which("git") or (notes / ".git").exists():
        return
    if not yes(t("\n  Wiki'nin geçmişi GitHub'daki özel (private) bir repoya yedeklensin mi?",
                 "\n  Back up the wiki's history to a private GitHub repo?")):
        return
    url = ask(t("  Repo adresi (önce github.com/new'de private repo aç; boş = sadece yerel geçmiş)",
                "  Repo URL (make a private repo at github.com/new first; empty = local history only)"), "")
    run = lambda *a: subprocess.run(["git", "-C", str(notes), *a], capture_output=True, text=True)
    run("init", "-b", "main")
    if not run("config", "user.email").stdout.strip():  # a fresh phone has no git identity; commits would fail
        run("config", "user.name", "Pentarch")
        run("config", "user.email", "pentarch@localhost")
    run("add", "-A")
    if run("commit", "-m", "wiki started").returncode != 0:
        print(t("  Commit olmadı; wiki geçmişi başlamadı.", "  Commit failed; the wiki history didn't start."))
        return
    if url.strip():
        run("remote", "add", "origin", url.strip())
        ok = run("push", "-u", "origin", "main").returncode == 0
        print(t("  Yedeklendi." if ok else "  Push olmadı; git'e giriş yaptığında gece kendisi dener.",
                "  Backed up." if ok else "  Push failed; once git is logged in, the nightly round retries."))


def main():
    global TR
    old = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    agent = old.get("agent", {})
    print(f"Pentarch setup. Home folder: {HOME}\n")

    lang = ask("Language / Dil", old.get("lang", "en"), ("en", "tr"))
    TR = lang == "tr"
    owner = ask(t("Senin adın", "Your name"), old.get("owner", ""))
    name = ask(t("Asistanın adı", "Assistant name"), old.get("name", "Pentarch"))
    notes = ask(t("Not klasörü (markdown)", "Notes folder (markdown)"), old.get("notes_dir", "~/storage/shared/Documents/wiki" if TERMUX else "~/notes"))

    HOME.mkdir(parents=True, exist_ok=True)  # agent_test runs inside it
    found = [c for c in CLIS if shutil.which(c)]
    print(t("Bulunan ajan CLI'ları: ", "Agent CLIs found: ") + (", ".join(found) or "-"))
    if not found:
        print(t("""  Hiçbiri PATH'te yok. Modelsiz de çalışan parçalar: başvuru panosu ve ilan taraması (tracker/README.md).
  Asistanın tamamı için birini kur ve giriş yap:
    claude   npm i -g @anthropic-ai/claude-code   (ücretli plan ya da API anahtarı)
    gemini   npm i -g @google/gemini-cli          (Google hesabıyla ücretsiz kota)
    codex    npm i -g @openai/codex               (ChatGPT hesabı)
    opencode npm i -g opencode-ai                  (kendi anahtarınla; OpenRouter ücretsiz modelleri de olur)""",
                """  None on PATH. The parts that work without a model: the application board and the job scan (tracker/README.md).
  For the full assistant, install one and log in:
    claude   npm i -g @anthropic-ai/claude-code   (paid plan or API key)
    gemini   npm i -g @google/gemini-cli          (free quota with a Google account)
    codex    npm i -g @openai/codex               (ChatGPT account)
    opencode npm i -g opencode-ai                  (your own key; OpenRouter free models work too)"""))
        if not yes(t("Yine de kuruluma devam edilsin mi?", "Continue the setup anyway?"), True):
            sys.exit(t("Tamam. CLI'ı kurunca python setup.py ile devam et.", "OK. Run python setup.py again once a CLI is installed."))
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
    bypass_ok = False
    if perm == "bypassPermissions":
        print(t("  UYARI: bypassPermissions ajana onaysız kabuk komutu çalıştırma izni verir; codex sandbox'sız, gemini yolo"
                " modunda çalışır. Gelen e-posta ya da web metnindeki bir talimat makinende komut çalıştırabilir.",
                "  WARNING: bypassPermissions lets the agent run shell commands without asking; codex runs without its"
                " sandbox and gemini in yolo mode. An instruction hidden in an e-mail or web page could run commands here."))
        bypass_ok = ask(t("  Onaylamak için 'onaylıyorum' yaz (boş = acceptEdits)", "  Type 'i confirm' to accept (empty = acceptEdits)"),
                        "").lower() in ("onaylıyorum", "i confirm")
        if not bypass_ok:
            perm = "acceptEdits"

    SECRETS.mkdir(parents=True, exist_ok=True)
    api = chat_api_setup(old.get("chat_api", {}))
    council_setup()
    telegram_setup()
    job_boards = career_setup(old, lang)
    mcp_servers = mcp_setup(old) if cli == "claude" else old.get("mcp_servers", {})

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
                     "permission_mode": perm, "bypass_confirmed": bypass_ok},
           "chat_api": api, "jobs_off": sorted(off), "job_boards": job_boards, "mcp_servers": mcp_servers}

    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    CONFIG.chmod(0o600)
    panel_settings = HOME / "ayarlar.json"  # the panel's own switches, once Pentarch has run
    if panel_settings.exists():
        a = json.loads(panel_settings.read_text(encoding="utf-8"))
        a["kapali_isler"] = sorted(set(a.get("kapali_isler", [])) - {"insa", "posta"} | off)
        panel_settings.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(notes).expanduser().mkdir(parents=True, exist_ok=True)
    if not any(Path(notes).expanduser().rglob("*.md")):
        print(t(f"""
  Hoş geldin, {cfg['owner']}! Not klasörün boş, yani henüz bir wikin yok.
  {cfg['name']} öğrendiklerini kalıcı tutmak için küçük bir wiki kullanır: kim olduğun, kararların,
  projelerin. Boş bir iskelet kurabilirim; sen konuştukça {cfg['name']} doldurur, her gece de kontrol eder.""",
                f"""
  Welcome, {cfg['owner']}! Your notes folder is empty, so you have no wiki yet.
  {cfg['name']} keeps what it learns in a small wiki: who you are, your decisions, your projects.
  I can set up an empty skeleton; {cfg['name']} fills it as you talk and checks it every night."""))
        if yes(t("  Wiki iskeleti kurulsun mu?", "  Set up the wiki skeleton?"), True):
            sys.path.insert(0, str(APP))
            import wiki
            made = wiki.kur(notes, cfg["owner"], cfg["name"], lang)
            print(t(f"  Kuruldu: {', '.join(made)}", f"  Created: {', '.join(made)}"))
    wiki_backup(Path(notes).expanduser())

    fill = {"{{APP}}": APP.as_posix(), "{{HOME}}": HOME.as_posix(), "{{NOTES}}": Path(notes).expanduser().as_posix(),
            "{{OWNER}}": cfg["owner"], "{{NAME}}": cfg["name"]}
    fill.update({"{{GOALS}}": t("(önümüzdeki aylar için 2-3 somut hedef, varsa son tarihleriyle)", "(2-3 concrete goals for the coming months, with deadlines if any)"),
                 "{{INTERESTS}}": t("(izlemem gereken konular, teknolojiler, fırsat türleri)", "(topics, technologies and kinds of opportunities to watch for)")})
    pf = REPO / "tracker" / "profile.json"
    if pf.exists():  # the career answers also seed the agent's profile.md
        prof = json.loads(pf.read_text(encoding="utf-8"))
        fill.update({"{{GOALS}}": t("şu rollerde iş bulmak: ", "find a role as ") + ", ".join(prof.get("target_roles") or []) +
                     (" (" + ", ".join(prof.get("locations") or []) + ")" if prof.get("locations") else ""),
                     "{{INTERESTS}}": ", ".join((prof.get("skills") or []) + (prof.get("target_roles") or []))})
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
    skills_setup(cli)

    if yes(t("\nPython paketleri kurulsun mu (sesli mesaj ve sesli cevap)?", "\nInstall the Python packages (voice in/out)?"), True):
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REPO / "requirements.txt")])

    if TERMUX:
        boot = Path.home() / ".termux" / "boot"
        if yes(t("Telefon açılınca Pentarch başlasın mı (Termux:Boot uygulaması gerekir)?",
                 "Start Pentarch when the phone boots (needs the Termux:Boot app)?"), True):
            boot.mkdir(parents=True, exist_ok=True)
            f = boot / "pentarch.sh"
            py, log = APP / "pentarch.py", HOME / "termux.log"
            # restart loop: a crash or Android's process killer doesn't leave it dead until the next reboot
            f.write_text("#!/data/data/com.termux/files/usr/bin/sh\ntermux-wake-lock\n"
                         f"nohup sh -c 'while true; do python -I \"{py}\" --quiet; sleep 30; done' >> '{log}' 2>&1 &\n",
                         encoding="utf-8")
            f.chmod(0o755)
        print(t("  Telefonda: Termux'u pil optimizasyonundan çıkar (Ayarlar > Uygulamalar > Termux > Pil > Kısıtlama yok),"
                "\n  yoksa Android gece süreci öldürür. Android 14+: Geliştirici seçenekleri > 'Alt süreç kısıtlamalarını devre dışı bırak'"
                "\n  aç. Termux:Boot uygulamasını bir kere aç. Wiki'yi Obsidian ile açmak için klasör: " + notes,
                "  On the phone: take Termux out of battery optimisation (Settings > Apps > Termux > Battery > Unrestricted),"
                "\n  or Android kills it at night. Android 14+: Developer options > 'Disable child process restrictions'."
                "\n  Open the Termux:Boot app once. To read the wiki in Obsidian, open this folder: " + notes))
        if not (Path.home() / "storage").exists():
            print(t("  UYARI: önce `termux-setup-storage` çalıştır, yoksa wiki Obsidian'ın göremediği bir klasörde kalır.",
                    "  WARNING: run `termux-setup-storage` first, or the wiki lands where Obsidian can't see it."))

    if os.name == "nt":
        icon = REPO / "assets" / "pentarch.ico"
        appdata = Path(os.environ["APPDATA"]) / "Microsoft/Windows"
        if yes(t("Windows açılınca Pentarch başlasın mı?", "Start Pentarch when Windows starts?"), True):
            shortcut(appdata / "Start Menu/Programs/Startup/Pentarch.lnk", f'-I "{APP / "pentarch.py"}" --quiet', icon)
        if yes(t("Masaüstüne panel kısayolu eklensin mi?", "Add a desktop shortcut for the panel?"), True):
            desk = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
            shortcut(desk / f"{cfg['name']}.lnk", f'-I "{APP / "pentarch.py"}" --panel', icon)

    todo = []
    if not shutil.which(cli):
        todo.append(t(f"{cli} CLI'ını kur ve giriş yap (yukarıdaki komut)", f"install {cli} and log in (command above)"))
    if not (SECRETS / "telegram.txt").exists():
        todo.append(t(f"Telegram token'ını {SECRETS / 'telegram.txt'} içine yaz", f"put your Telegram bot token in {SECRETS / 'telegram.txt'}"))
    print(t("\nBitti.", "\nDone."))
    if todo:
        print(t("Asistanı başlatmadan önce:", "Before starting the assistant:") + "".join(f"\n  - {x}" for x in todo))
    print(t(f"""Başlatmak için:  python -I "{APP / 'pentarch.py'}"
Sonra Telegram'dan botuna herhangi bir mesaj at: ilk yazan sohbet sahip olur.""", f"""Start it with:  python -I "{APP / 'pentarch.py'}"
Then send any message to your bot from Telegram: the first chat that writes becomes the owner."""))
    if (REPO / "tracker" / "config.json").exists():
        print(t(f"""Modelsiz çalışan kariyer parçaları (bir CLI gerekmez):
  ilanları tara:   python -I "{REPO / 'tracker' / 'scan.py'}" --config "{REPO / 'tracker' / 'config.json'}"
  panoyu oluştur:  python -I "{REPO / 'tracker' / 'build.py'}" --config "{REPO / 'tracker' / 'config.json'}"   (sonra tracker/out/index.html'i aç)""",
                f"""Career parts that need no model (no CLI required):
  scan the boards:  python -I "{REPO / 'tracker' / 'scan.py'}" --config "{REPO / 'tracker' / 'config.json'}"
  build the board:  python -I "{REPO / 'tracker' / 'build.py'}" --config "{REPO / 'tracker' / 'config.json'}"   (then open tracker/out/index.html)"""))
    print(t(f"Ayarlar: {CONFIG}   Hafıza ve istemler: {HOME}", f"Settings: {CONFIG}   Memory and prompts: {HOME}"))

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        sys.exit(t("\nİptal edildi.", "\nCancelled."))
