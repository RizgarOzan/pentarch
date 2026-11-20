"""Pentarch setup: asks a few questions, writes the runtime home and adds the start-up shortcuts.

    python setup.py            interactive
    python setup.py --force    also overwrite the prompt/memory files already in the home folder
    python setup.py --upgrade  no questions: install skills and agents that are new since the last setup (run by updates)

Re-running it is safe: answers default to what is already configured and your memory files are kept.
Nothing here leaves your computer; the Telegram token and API key go to <home>/secrets, never into the repo.
"""
import getpass
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

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


def _input(prompt):
    """input() where Ctrl+C asks before quitting, so one stray press (or a copy attempt) doesn't throw the answers away."""
    while True:
        try:
            return input(prompt)
        except KeyboardInterrupt:
            if input(t("\n  Kurulumdan çıkılsın mı? [e/H]: ", "\n  Quit setup? [y/N]: ")).strip().lower() in EVET:
                raise  # a second Ctrl+C at this question quits too


def ask(q, default="", choices=None):
    shown = "/".join(choices) + (f", Enter = {default}" if default else "") if choices else default
    hint = f" [{shown}]" if shown else ""
    while True:
        a = _input(f"{q}{hint}: ").strip() or default
        if not choices or a in choices:
            return a
        print(t("  şunlardan biri: ", "  pick one of: ") + ", ".join(choices))


EVET = {"y", "yes", "e", "evet", "s", "si", "sí", "sim", "j", "ja", "o", "oui", "d", "da", "ok"}  # people answer in their own language


def yes(q, default=False):
    a = _input(f"{q} [{t('E/h', 'Y/n') if default else t('e/H', 'y/N')}]: ").strip().lower().rstrip(".!")
    return default if not a else a in EVET


QUICK = False  # quick setup: the questions below that go through opt() take their default
STEP = [0, 6]


def opt(q, default=False):
    return default if QUICK else yes(q, default)


def step(tr, en):
    STEP[0] += 1
    print(f"\n== {t('Adım', 'Step')} {STEP[0]}/{STEP[1]}: {t(tr, en)} ==")


def secret(q):
    """Hidden input; falls back to plain input when stdin is piped (getpass reads the console on Windows)."""
    if sys.stdin.isatty():
        print(t("  (yazdıkların görünmez; yapıştır ve Enter'a bas. Windows'ta sağ tık = yapıştır)",
                "  (your typing is hidden; paste and press Enter. On Windows, right-click pastes)"))
        v = getpass.getpass(q)
        if v:  # the typing is hidden, so say it arrived
            print(t(f"  Alındı ({len(v.strip())} karakter).", f"  Got it ({len(v.strip())} characters)."))
        return v
    return input(q)


def get_json(url, key=None, timeout=10):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


sys.path.insert(0, str(APP))
import koltuk  # noqa: E402  (presets and the council-seat helpers; config.py resolves the same HOME)
PRESETS = koltuk.PRESETS  # name -> (base_url, key env, suggested model, where to get the key)
import anahtar  # noqa: E402  (step-by-step key guide: pages, format check, free test call)


def read_env(path):
    return dict(l.split("=", 1) for l in path.read_text(encoding="utf-8").splitlines() if "=" in l) if path.exists() else {}


def chat_api_setup(api, beyin=False):
    """Picks an endpoint, saves its key and checks it answers on /models. Returns the chat_api dict.
    beyin: this endpoint is the whole brain (agent.cli = "api"), so the chat's personal data goes to it."""
    key_env = api.get("key_env", "PENTARCH_CHAT_KEY")
    if beyin:
        print(t("\nAsistan bu servisle düşünür. Kendi makinende: ollama ya da lmstudio. Kendi sunucun (vLLM vb.): custom.",
                "\nThe assistant thinks with this service. On this machine: ollama or lmstudio. Your own server (vLLM etc.): custom."))
    else:
        print(t("\nUcuz tek seferlik işler için isteğe bağlı bir OpenAI uyumlu servis (sohbet ajanla devam eder).",
                "\nOptional OpenAI-compatible service for cheap one-shot work (the chat itself stays on the agent)."))
    cur = next((k for k, v in PRESETS.items() if v[0] == api.get("base_url")), "custom" if api.get("base_url") else
               ("ollama" if beyin else "none"))
    pick = ask(t("Servis", "Service"), cur, (*PRESETS, "custom", "none"))
    if pick == "none":
        return {"base_url": "", "model": "", "key_env": key_env}
    base, preset_env, model, _ = PRESETS.get(pick, (api.get("base_url", ""), key_env, api.get("model", ""), ""))
    need_key = bool(preset_env)
    if pick == "custom":
        base = ask("base_url (…/v1)", base)
    env_file = SECRETS / "keys.env"
    saved = read_env(env_file)
    key = os.environ.get(key_env) or saved.get(key_env, "")
    if pick in anahtar.GUIDES and not need_key:
        anahtar.show(pick, t, yes)
    if need_key and (not key or yes(t("Kayıtlı API anahtarı değiştirilsin mi?", "Replace the saved API key?"))):
        if pick in anahtar.GUIDES:
            new = anahtar.ask(pick, t, yes, secret)
        else:
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
    out = {"base_url": base, "model": model, "key_env": key_env}
    if pick in ("ollama", "lmstudio"):  # runs on this machine; trusted by preset, never by a localhost address
        out["trusted"] = True
    elif beyin and yes(t("Sohbetin kişisel bilgileri bu servise gidecek. Bu servis senin ya da güvendiğin bir yer mi (veriyle eğitim yapmıyor)?",
                         "The chat's personal data will go to this service. Is it yours, or one you trust not to train on your data?"),
                       api.get("trusted", False)):
        out["trusted"] = True
    elif beyin:
        print(t("  Güvenilir işaretlenmedi: sohbet bu servise kişisel bilgi göndermez, yani cevap veremez. Sonra config'te \"trusted\": true.",
                "  Not marked trusted: the chat won't send personal data to it, so it can't answer. Later: \"trusted\": true in config."))
    return out


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
    tk = anahtar.ask("telegram", t, yes, secret, "Bot token")
    if not tk:
        print(t("  Token'ı sonra secrets/telegram.txt içine de yazabilirsin.", "  You can also put the token in secrets/telegram.txt later."))
        return
    tok.write_text(tk + "\n", encoding="utf-8")
    tok.chmod(0o600)
    pair = SECRETS / "telegram-pair.txt"
    if not pair.exists():
        import secrets as _s
        pair.write_text(_s.token_hex(8), encoding="utf-8")
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
        print(t(f"  ! {cli} cevap vermedi: {last[0][:160]}", f"  ! {cli} did not answer: {last[0][:160]}"))
    return bool(ok)


NPM_PKG = {"claude": "@anthropic-ai/claude-code", "gemini": "@google/gemini-cli", "codex": "@openai/codex", "opencode": "opencode-ai"}
LOGIN = {  # cli -> (command, what to do in it)
    "claude": ("claude", ("Tarayıcı açılır (açılmazsa pencerede /login yaz); Claude hesabınla gir.",
                          "A browser opens (if not, type /login in the window); sign in with your Claude account.")),
    "gemini": ("gemini", ("Siyah bir pencere açılır: 'Login with Google' seçeneğinde Enter'a bas, açılan tarayıcıda Google hesabınla gir, "
                          "sonra o pencereyi kapat.",
                          "A black window opens: press Enter on 'Login with Google', sign in with your Google account in the browser "
                          "that opens, then close that window.")),
    "codex": ("codex login", ("Tarayıcıda ChatGPT hesabınla gir.", "Sign in with your ChatGPT account in the browser.")),
    "opencode": ("opencode auth login", ("Listeden bir servis seç, anahtarını yapıştır (ücretsiz OpenRouter anahtarı da olur).",
                                         "Pick a provider from the list and paste its key (a free OpenRouter key works).")),
}


def preflight():
    """Says what is missing before the questions start, and where to get it."""
    missing = [(n, url, why) for n, url, why in (
        ("git", "https://git-scm.com/downloads", t("otomatik güncelleme için", "for auto-update")),
        ("npm", "https://nodejs.org/", t("ajan CLI'ını kurmak için; Node.js ile gelir", "to install the agent CLI; comes with Node.js")))
        if not shutil.which(n)]
    for n, url, why in missing:
        where = f"pkg install {'nodejs' if n == 'npm' else n}" if TERMUX else url
        print(t(f"  ! {n} yok ({why}): {where}", f"  ! {n} is missing ({why}): {where}"))
    if not missing:
        print(t("  Python, git ve npm hazır.", "  Python, git and npm are ready."))


def hazir(cli):
    """The brain can run: its CLI is on PATH, or it is the built-in API loop (needs no program)."""
    return cli == "api" or bool(shutil.which(cli))


def cli_setup(cli):
    """Installs the agent CLI with npm if asked, walks through the login and tests it. True once it answers."""
    if cli == "api":  # no program to install; chat_api_setup asks for the endpoint
        return True
    if not shutil.which(cli):
        cmd = f"npm i -g {NPM_PKG[cli]}"
        if not shutil.which("npm"):
            print(t(f"  ! {cli} kurulu değil ve npm yok. Önce Node.js'i kur (https://nodejs.org/), sonra: {cmd}",
                    f"  ! {cli} is not installed and npm is missing. Install Node.js first (https://nodejs.org/), then: {cmd}"))
            return False
        if not yes(t(f"{cli} kurulu değil. Şimdi kurulsun mu ({cmd})?", f"{cli} is not installed. Install it now ({cmd})?"), True):
            return False
        if subprocess.run([shutil.which("npm"), *cmd.split()[1:]]).returncode:
            fix = ("" if os.name == "nt" else t(
                " İzin hatasıysa (EACCES): `npm config set prefix ~/.npm-global` çalıştır, sonra "
                "`echo 'export PATH=\"$HOME/.npm-global/bin:$PATH\"' >> ~/.zprofile` (bash'te ~/.bashrc), yeni terminal aç, yeniden dene.",
                " If it was a permission error (EACCES): run `npm config set prefix ~/.npm-global`, then "
                "`echo 'export PATH=\"$HOME/.npm-global/bin:$PATH\"' >> ~/.zprofile` (~/.bashrc on bash), open a new terminal, try again."))
            print(t(f"  ! npm kurulumu başarısız oldu; yukarıdaki hataya bak.{fix}",
                    f"  ! The npm install failed; see the error above.{fix}"))
            return False
        if not shutil.which(cli):  # a fresh npm prefix may not be on this process's PATH yet; look there before giving up
            try:
                prefix = subprocess.run([shutil.which("npm"), "prefix", "-g"], capture_output=True, text=True, timeout=30).stdout.strip()
                os.environ["PATH"] = os.pathsep.join([prefix, str(Path(prefix) / "bin"), os.environ.get("PATH", "")])
            except Exception:
                pass
        if not shutil.which(cli):
            print(t("  ! Kurulum bitti ama komut bulunamadı; yeni bir terminal açıp setup'ı yeniden çalıştır.",
                    "  ! The install finished but the command isn't found; open a new terminal and run setup again."))
            return False
    if not yes(t(f"{cli} kısa bir mesajla denensin mi (giriş yapılmış mı diye)?",
                 f"Send {cli} a short test message (checks that it is logged in)?"), True):
        return False
    while not agent_test(cli):
        login, how = LOGIN[cli]
        print(t(f"  Giriş yapman gerekiyor: bir terminalde `{login}` çalıştır. {how[0]}",
                f"  You need to log in: run `{login}` in a terminal. {how[1]}"))
        if (os.name == "nt" or sys.platform == "darwin") and yes(t("  Giriş için yeni bir pencere açılsın mı?", "  Open a new window for the login?"), True):
            if os.name == "nt":
                subprocess.Popen(f'start "{cli} login" cmd /k {login}', shell=True)
            else:
                subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{login}"', "-e", 'tell application "Terminal" to activate'])
            print(t("  Girişi o pencerede bitir, pencereyi kapat, sonra buraya dönüp Enter'a bas.",
                    "  Finish the login in that window, close it, then come back here and press Enter."))
        if not yes(t("  Girişi bitirince yeniden denensin mi? (hayır = sonra)", "  Test again once you are logged in? (no = later)"), True):
            return False
    return True


def free_keys_setup(api):
    """Free keys for cheap jobs and council seats; each one opens its page and walks through it. Returns chat_api."""
    print(t("  İsteğe bağlı ücretsiz ekstralar; emin değilsen geç, asistan bunlarsız da tam çalışır.",
            "  Optional free extras; not sure? skip them, the assistant works fully without them."))
    for name in ("openrouter", "groq", "nvidia"):
        base, env, model, _ = PRESETS[name]
        if koltuk.has_key(env):
            print(t(f"  {name}: anahtar zaten kayıtlı.", f"  {name}: key already saved."))
            continue
        print(f"\n{name}: {t(*anahtar.GUIDES[name]['free'])}")
        bedava = t("deneme kredili", "trial-credit") if name == "nvidia" else t("ücretsiz", "free")  # NVIDIA's credits run out
        if not yes(t(f"  {bedava.capitalize()} {name} anahtarı alınsın mı (sayfası açılır)?", f"  Get a {bedava} {name} key (opens its page)?"), not QUICK):
            continue
        key = anahtar.ask(name, t, yes, secret)
        if not key:
            continue
        koltuk.save_key(env, key)
        koltuk.add(name, name, check=False)
        if not api.get("base_url"):
            api = {"base_url": base, "model": model, "key_env": env}
    return api


def pair_and_start(cli, name):
    """Waits for the owner's /start <code> in Telegram, then offers to start the assistant in the background."""
    import tg
    state = tg.load_state()
    if tg.TOKEN_FILE.exists() and state.get("chat_id") is None:
        try:
            bot = tg.api("getMe")["username"]
        except Exception as e:
            bot = None
            print(t(f"  ! Telegram'a ulaşılamadı ({e}); eşleşme asistan çalışınca da olur.",
                    f"  ! Could not reach Telegram ({e}); pairing also works once the assistant runs."))
        if bot:
            code = tg.pair_code()
            link = f"https://t.me/{bot}?start={code}"
            print(t(f"  Botunu kendine bağla: {link} adresini aç, Telegram'da Start'a bas (ya da bota /start {code} yaz).",
                    f"  Claim your bot: open {link} and press Start in Telegram (or send the bot /start {code})."))
            if anahtar.ekran() and yes(t("  Bağlantı şimdi açılsın mı?", "  Open the link now?"), True):
                webbrowser.open(link)
            print(t("  Bekliyorum, en çok 3 dakika (Ctrl+C ile geç)...", "  Waiting up to 3 minutes (Ctrl+C skips)..."))
            end = time.time() + 180
            try:
                while time.time() < end and state.get("chat_id") is None:
                    for upd in tg.api("getUpdates", http_timeout=40, offset=state["offset"], timeout=20):
                        state["offset"] = upd["update_id"] + 1
                        msg = upd.get("message") or {}
                        if msg.get("chat", {}).get("type") != "private":
                            continue
                        if msg.get("text", "").strip() == f"/start {code}":
                            state["chat_id"] = msg["chat"]["id"]
                        else:  # a bare /start or a typo: say what is missing instead of staying silent
                            tg.api("sendMessage", chat_id=msg["chat"]["id"],
                                   text=t("Kurulum ekranındaki kodu bekliyorum: /start ve yanında o kod.",
                                          "I'm waiting for the code shown in setup: /start followed by that code."))
                    tg.save_state(state)
            except KeyboardInterrupt:
                print()
            except Exception as e:
                print(t(f"  ! Telegram okunamadı ({e}).", f"  ! Could not read Telegram ({e})."))
            if state.get("chat_id") is not None:
                tg.api("sendMessage", chat_id=state["chat_id"], text=t(f"Eşleştik. Ben {name}, buradan yazabilirsin.\n\n",
                                                                       f"Paired. I'm {name}; you can write to me here.\n\n") + tg.ornekler(TR)
                       + ("" if hazir(cli) else "\n\n" + t(f"Not: {cli} kurulu ya da girişi yapılmış olana kadar cevap veremem.",
                                                          f"Note: I can't answer until {cli} is installed and logged in.")))
                print(t("  Eşleşme tamam; bota bir selam mesajı gönderildi.", "  Paired; the bot sent you a hello."))
            else:
                print(t(f"  Eşleşme olmadı. Asistan çalışırken bota /start {code} yazman yeter.",
                        f"  Not paired yet. Send the bot /start {code} while the assistant runs."))
    if not hazir(cli) or (os.name == "posix" and not TERMUX):
        return False
    if TERMUX and shutil.which("pgrep") and subprocess.run(["pgrep", "-f", "pentarch.py"], capture_output=True).returncode == 0:
        print(t(f"  {name} zaten çalışıyor.", f"  {name} is already running."))  # a second restart loop would spin forever
        return True
    if not yes(t(f"{name} şimdi arka planda başlatılsın mı?", f"Start {name} in the background now?"), True):
        return False
    flags = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}  # detached
    # on the phone the first start gets the same wake lock and restart loop as a boot, not a bare process Android kills
    cmd = ["sh", "-c", termux_boot_script(sys.executable, APP / "pentarch.py", HOME / "termux.log")] if TERMUX \
        else [sys.executable, "-I", str(APP / "pentarch.py"), "--quiet"]
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    print(t(f"  Başladı. Telegram'dan yazınca {name} cevap verir.", f"  Started. Write to {name} in Telegram and it answers."))
    return True


LEVELS = {  # answer -> (seniority words scan.py needs in a title, max years a posting may ask for, job_boards titles filter, title words to drop)
    "intern": (["intern"], 1, ["intern", "internship", "staj", "stajyer", "working student", "trainee"], None),
    "entry": (["intern", "junior", "entry level"], 2, ["intern", "internship", "junior", "graduate", "new grad", "entry", "trainee"], None),
    "mid": ([], 5, [], ["lead", "head", "principal", "staff", "director", "manager", "chief"]),
    "any": ([], 99, [], []),
}
# Turkish companies whose public boards answered with Turkey postings (checked 2026-11-20). Youthall, Kariyer.net and
# LinkedIn, where most Turkish internships are, have no open feed, so setup names them for a manual look instead.
TR_BOARDS = {"lever": ["trendyol", "insiderone", "dreamgames", "iyzico", "picus"], "ashby": ["codeway", "good-job-games"],
             "workable": ["ace-games"]}
TR_PLACES = ("türkiye", "turkiye", "turkey", "istanbul", "i̇stanbul", "ankara", "izmir", "i̇zmir")


def csv(q, default):
    return [x.strip() for x in ask(q, ", ".join(default)).split(",") if x.strip()]


# reply_lang is written in words ("Deutsch"); the CV wants a code. Same table as config.LANG_CODES (setup does not import config).
REPLY_CODES = {"deutsch": "de", "german": "de", "español": "es", "espanol": "es", "spanish": "es"}


def career_setup(old_cfg, lang, asked=False):
    """Target roles, level, places, skills and job boards, once: tracker/profile.json for the scan and the agent,
    job_boards in pentarch.json for the watch routine. Re-runs default to the saved answers. Returns job_boards."""
    tracker = REPO / "tracker"
    pf = tracker / "profile.json"
    cur = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    boards_old = old_cfg.get("job_boards") or {}
    print(t("\nKariyer: ilan taraması, başvuru panosu ve asistanın ilanlar hakkındaki yorumları bu cevaplara göre çalışır (sonra: tracker/profile.json).",
            "\nCareer: the job scan, the application board and the assistant's verdicts on postings follow these answers (later: tracker/profile.json)."))
    if not asked and not yes(t("Kariyer takibi kurulsun mu?", "Set up the career tracker?"), True):
        return boards_old
    roles = []
    while not roles:  # no default: a preset role would quietly scan the wrong jobs for anyone outside software
        roles = csv(t("Hedef roller, ilan başlıklarında yazdığı gibi (ör. junior data analyst, UX designer; virgülle)",
                      "Target roles as job titles write them (e.g. junior data analyst, UX designer; comma separated)"),
                    cur.get("target_roles") or [])
    sen = cur.get("seniority") or []
    cur_level = ("intern" if sen == ["intern"] else "entry" if sen else "mid" if cur and int(cur.get("max_years", 2)) <= 5
                 else "any" if cur else "entry")
    level = ask(t("Seviye (intern: yalnızca staj; entry: stajyer/junior, en çok 2 yıl isteyen ilanlar; mid: 5 yıla kadar, lead/müdür yok; any: hepsi. "
                    "Başka meslekten geçiyorsan mid seç: entry, 'junior' yazmayan ilanları atar)",
                  "Level (intern: internships only; entry: intern/junior, postings asking 2 years at most; mid: up to 5, no lead/manager; any: all. "
                  "Switching careers? pick mid: entry drops every title without 'junior')"),
                cur_level, tuple(LEVELS))
    city = ask(t("Yaşadığın şehir, ülke", "City, country you live in"), (cur.get("applicant") or {}).get("city", ""))
    home_city = city.split(",")[0].strip()
    locs = csv(t("İş aradığın yerler (remote, şehir, ülke; taşınırsın diye 'relocation ok' ekle)",
                 "Places to work (remote, city, country; add 'relocation ok' if you would move)"),
               cur.get("locations") or ([home_city] if home_city else []) + ["remote"])
    skills = csv(t("Becerilerin, ilanlarda yazıldığı gibi tek tek ve mülakatta savunabildiklerin (Unity, Unity 6 değil; virgülle)",
                   "Your skills, one name each as postings write them, only ones you can defend in an interview (Unity, not Unity 6; comma separated)"),
                 cur.get("skills") or [])
    example = json.loads((tracker / "profile.example.json").read_text(encoding="utf-8"))
    breakers = csv(t("İlanı direkt eleyen kelimeler (virgülle)", "Words that rule a posting out (comma separated)"),
                   (cur.get("signals") or example["signals"]).get("deal_breakers") or [])
    cb = cur.get("boards") or {}
    if QUICK:  # slugs are an expert question; quick setup keeps what was there and starts on the open feeds
        boards = {k: cb.get(k) or boards_old.get(k) or [] for k in ("greenhouse", "lever", "ashby", "workable")}
    else:
        print(t("  İzlenecek şirket panoları; slug, kariyer sayfasının adresindeki son parça (boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>, apply.workable.com/<slug>). Boş olabilir.",
                "  Company boards to watch; the slug is the last part of the careers URL (boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>, apply.workable.com/<slug>). May be empty."))
        boards = {k: csv(f"  {k}", cb.get(k) or boards_old.get(k) or []) for k in ("greenhouse", "lever", "ashby", "workable")}
    seniority, years, titles, exclude = LEVELS[level]
    sys.path.insert(0, str(tracker))
    import build  # noqa: E402
    build.init(tracker)
    prof = json.loads(pf.read_text(encoding="utf-8"))
    prof.pop("_", None)  # the example's "copy me" note
    if any(p in " ".join([city, *locs]).lower() for p in TR_PLACES):
        if any(l.lower() in ("türkiye", "turkiye") for l in locs) and not any(l.lower() == "turkey" for l in locs):
            locs.append("Turkey")  # postings write the English name
        names = ", ".join(s for v in TR_BOARDS.values() for s in v)
        print(t(f"  Türkiye'de açık ilan panosu olan şirketler: {names}.", f"  Companies in Turkey with an open job board: {names}."))
        if opt(t("  Bunlar da taransın mı?", "  Scan these too?"), True):
            for k, slugs in TR_BOARDS.items():
                boards[k] = list(dict.fromkeys([*(boards.get(k) or []), *slugs]))
        print(t("  Türkiye'deki stajların çoğu Youthall, Kariyer.net ve LinkedIn'de; onların açık bir akışı yok, oralara arada elle bak.",
                "  Most internships in Turkey are on Youthall, Kariyer.net and LinkedIn; they have no open feed, so check them by hand now and then."))
    prof.update(target_roles=roles, seniority=seniority, locations=locs, skills=skills, max_years=years,
                boards={**(prof.get("boards") or {}), **boards})
    if not any(v for k, v in prof["boards"].items() if not k.startswith("_")):  # nothing to scan: start with the open feeds
        prof["boards"].update(remotive=[""], arbeitnow=[""])
        print(t("  Şirket panosu yok; tarama Remotive ve Arbeitnow'un açık ilanlarıyla başlar.",
                "  No company boards; the scan starts with the open Remotive and Arbeitnow feeds."))
    if exclude is not None:  # the example's exclude list is for entry level
        prof["exclude"] = exclude
    prof.setdefault("cv", {})["language"] = ask(t("CV ve ön yazı dili (en, tr, de, es)", "CV and cover letter language (en, tr, de, es)"),
                                                (cur.get("cv") or {}).get("language") or REPLY_CODES.get((old_cfg.get("reply_lang") or "").strip().lower()) or lang, ("en", "tr", "de", "es"))
    prof["applicant"] = applicant_setup(cur.get("applicant") or {}, city, locs)
    if str(prof["applicant"].get("needs_sponsorship", "")).lower().startswith(("y", "e")):  # yes / evet
        breakers += [p for p in NO_SPONSOR if p not in breakers]
    prof.setdefault("signals", {})["deal_breakers"] = breakers
    pf.write_text(json.dumps(prof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(t(f"  Yazıldı: {pf}. Pentarch her sabah 08:30'da ilanları tarar ve panoyu yeniler (panelde pano düğmesi);\n"
            "  elle: python -I tracker/scan.py --config tracker/config.json",
            f"  Written: {pf}. Pentarch scans the boards and refreshes the board every morning at 08:30 (board button\n"
            "  in the panel); by hand: python -I tracker/scan.py --config tracker/config.json"))
    return {**boards_old, **boards, "titles": titles, "fields": [],
            "locations": [l for l in locs if not l.lower().startswith("relocation")]}


IMAP_HOSTS = {"gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com", "yandex.com": "imap.yandex.com",
              "yandex.com.tr": "imap.yandex.com", "icloud.com": "imap.mail.me.com", "me.com": "imap.mail.me.com",
              "yahoo.com": "imap.mail.yahoo.com"}


def mail_setup(old):
    """Lets the mail check routine (posta) read the inbox over IMAP, read-only. Returns the gateways dict;
    the e-mail door (chat by mail) stays as it was."""
    gw = {**(old.get("gateways") or {})}
    em = {**(gw.get("email") or {})}
    print(t("\nPosta: asistan gelen kutundaki maillere (kimden, konu, ilk birkaç satır) bakıp beklediğin bir cevap, fatura ya da son tarih gibi\n"
            "  önemli olanları Telegram'dan haber verir. Yalnızca okur; hiçbir şeyi okundu işaretlemez, silmez, göndermez.\n"
            "  Bu satırlar okunmak için seçtiğin yapay zekâ servisine gider.",
            "\nMail: the assistant looks at your inbox (sender, subject, first few lines) and tells you on Telegram about the ones\n"
            "  that matter, like a reply you're waiting for, a bill or a deadline. It only reads; it marks, deletes and sends nothing.\n"
            "  Those lines go to the AI service you picked, so it can read them."))
    if not yes(t("Gelen kutun okunsun mu?", "Read your inbox?"), bool(em.get("imap_host"))):
        return gw, False
    user = ask(t("E-posta adresin", "Your email address"), em.get("user", ""))
    host = IMAP_HOSTS.get(user.rpartition("@")[2].lower(), em.get("imap_host", ""))
    if user.lower().endswith(("@outlook.com", "@hotmail.com", "@live.com")):
        print(t("  Outlook/Hotmail kutusu şimdilik okunamıyor (Microsoft şifreyle girişi kapattı). Geri kalan her şey çalışır;\n"
                "  posta özeti istersen Outlook'ta Gmail adresine yönlendirme açıp burada o adresi ver.",
                "  An Outlook/Hotmail inbox can't be read for now (Microsoft turned off password sign-in). Everything else works;\n"
                "  for the mail summary, forward Outlook to a Gmail address and give that one here."))
        return gw, False
    host = ask(t("IMAP sunucusu", "IMAP server"), host)
    if "gmail" in host:
        print(t("  Gmail normal şifreni kabul etmez, 16 harflik bir uygulama şifresi ister:\n"
                "  1) Hesabında iki adımlı doğrulama açık olmalı.\n  2) https://myaccount.google.com/apppasswords adresini aç, bir ad yaz (Pentarch), Oluştur'a bas.\n"
                "  3) Çıkan 16 harfi aşağıya yapıştır.",
                "  Gmail won't take your normal password; it needs a 16-letter app password:\n"
                "  1) Two-step verification must be on for the account.\n  2) Open https://myaccount.google.com/apppasswords, type a name (Pentarch), press Create.\n"
                "  3) Paste the 16 letters below."))
    print(t("  Bilmen gereken: bu şifre posta kutuna tam erişim verir (okuma, gönderme, silme). Pentarch onu yalnızca\n"
            "  posta okumak için kullanır ve ajana vermez; istediğin an aynı sayfadan iptal edebilirsin.",
            "  Worth knowing: this password gives full access to the mailbox (read, send, delete). Pentarch only uses it to\n"
            "  read mail and never hands it to the agent; you can revoke it on the same page at any time."))
    env =em.get("password_env") or "PENTARCH_MAIL_PASSWORD"
    have = bool(read_env(SECRETS / "keys.env").get(env))
    ask_pw = not have or yes(t("Kayıtlı posta şifresi değiştirilsin mi?", "Replace the saved mail password?"))
    gw["email"] = {**em, "imap_host": host, "user": user, "password_env": env}
    for _ in range(3):
        if ask_pw:
            pw = secret(t(f"Uygulama şifresi (gizli, secrets/keys.env içine {env} olarak yazılır; boş geçer): ",
                          f"App password (hidden, saved to secrets/keys.env as {env}; empty skips): ")).replace(" ", "")
            if not pw:
                return gw, False
            koltuk.save_key(env, pw)
        try:
            import imaplib
            m = imaplib.IMAP4_SSL(host, timeout=20)
            m.login(user, read_env(SECRETS / "keys.env").get(env) or os.environ.get(env, ""))  # the file first: it holds what was just typed
            m.logout()
            print(t("  Bağlantı tamam.", "  Connected."))
            return gw, True
        except Exception as e:
            print(t(f"  ! Giriş olmadı ({e}).", f"  ! Sign-in failed ({e})."))
        if not yes(t("  Şifreyi yeniden girmek ister misin?", "  Type the password again?"), True):
            break
        ask_pw = True
    print(t("  Posta kontrolü kapalı kalıyor; şifreyi düzeltince kurulumu yeniden çalıştır.",
            "  The mail check stays off; run setup again once the password is right."))
    return gw, False


def small_business_setup(notes, lang):
    """Optional: the calendar link (PENTARCH_ICAL) and starter shift / receivables files, for people running a shop."""
    if not opt(t("  Takvim bağlansın mı (ders programı, iş, dükkân)? Vardiya ve alacak dosyaları da açılır.",
                 "  Link a calendar (class timetable, work, shop)? Starter shift and receivables files come with it."), False):
        return
    if not read_env(SECRETS / "keys.env").get("PENTARCH_ICAL"):
        url = ask(t("  Gizli iCal adresi (Google Takvim > ayarlar > takvimi entegre et; boş geçer)",
                    "  Secret iCal address (Google Calendar > settings > integrate calendar; empty skips)"))
        if url.startswith("http"):
            koltuk.save_key("PENTARCH_ICAL", url.strip())
            print(t("  Takvim adresi secrets/keys.env içine yazıldı.", "  Calendar address saved to secrets/keys.env."))
    tr = lang == "tr"
    files = {
        ("vardiyalar.md" if tr else "shifts.md"): t(
            "# Vardiyalar\n\nHer vardiya bir satır: TARİH | KİŞİ | BAŞLANGIÇ-BİTİŞ | not\nÖrnek satırı kopyala, tarihi ve adı değiştir:\n\n<!-- 2026-01-05 | Ali | 07:00-15:00 | açılış -->\n",
            "# Shifts\n\nOne shift per line: DATE | PERSON | START-END | note\nCopy the example, change the date and name:\n\n<!-- 2026-01-05 | Ali | 07:00-15:00 | opening -->\n"),
        ("alacaklar.md" if tr else "receivables.md"): t(
            "# Alacaklar\n\nBir satır: TARİH | KİM | TUTAR | not (sana borçlu olanlar)\nÖdediğin faturalar için başa borc yaz: borc TARİH | KİM | TUTAR\nÖdenince satırın başına - [x] koy.\n",
            "# Receivables\n\nOne line: DATE | WHO | AMOUNT | note (people who owe you)\nBills you owe start with owe: owe DATE | WHO | AMOUNT\nMark paid ones with - [x] at the start.\n"),
    }
    if opt(t("  Ödev ve sınav takibi de açılsın mı (öğrenciysen)?", "  Track assignments and exams too (if you study)?"), False):
        files[("dersler.md" if tr else "study.md")] = t("# Dersler\n\nBir satır: TARİH | DERS | ne (ödev, sınav, vize...)\nBitince satırın başına - [x] koy. Sınav yazan satırlar için kalan gün sayılır.\n\n<!-- 2026-12-05 | Calculus | vize sınavı -->\n", "# Study\n\nOne line: DATE | COURSE | what (assignment, exam, midterm...)\nMark done with - [x] at the start. Lines that name an exam get a day countdown.\n\n<!-- 2026-12-05 | Calculus | midterm exam -->\n")
    for name, body in files.items():
        if not (notes / name).exists():
            (notes / name).write_text(body, encoding="utf-8")
    print(t(f"  Örnek dosyalar not klasöründe: {notes}", f"  Starter files are in your notes folder: {notes}"))


def doors_setup(gw):
    """Optional Slack, Discord and Signal doors (full setup only). README "Turning on Slack, Signal or Discord" has
    the longer walk-through."""
    gw = {**gw}
    print(t("\nDiğer kapılar: Telegram'ın yanında Slack, Discord ya da Signal'den de yazabilirsin. Hepsi yalnız sana cevap verir.\n"
            "  Adımların uzun hâli README'de (Turning on Slack, Signal or Discord).",
            "\nOther doors: besides Telegram you can also write from Slack, Discord or Signal. Each answers only you.\n"
            "  The long walk-through is in the README (Turning on Slack, Signal or Discord)."))
    for ad, ad_tr in (("slack", "Slack"), ("discord", "Discord"), ("signal", "Signal")):
        eski = {**(gw.get(ad) or {})}
        if not yes(t(f"{ad_tr} açılsın mı?", f"Turn on {ad_tr}?"), bool(eski.get("enabled"))):
            if eski:
                gw[ad] = {**eski, "enabled": False}
            continue
        if ad == "signal":
            if not shutil.which(eski.get("cli") or "signal-cli"):
                print(t("  signal-cli bulunamadı. Kur (https://github.com/AsamK/signal-cli), bir numara kaydet ya da telefonuna bağla,\n"
                        "  sonra kurulumu yeniden çalıştır. Signal şimdilik kapalı.",
                        "  signal-cli not found. Install it (https://github.com/AsamK/signal-cli), register a number or link it to your\n"
                        "  phone, then run setup again. Signal stays off for now."))
                continue
            hesap = ask(t("signal-cli'daki numara (+90...)", "Number signal-cli uses (+1...)"), eski.get("account", ""))
            sahip = ask(t("Senin numaran (aynıysa Kendime Not'tan konuşursun)", "Your number (if it's the same, you chat in Note to Self)"),
                        eski.get("owner") or hesap)
            gw[ad] = {**eski, "enabled": bool(hesap and sahip), "account": hesap, "owner": sahip}
            continue
        if ad == "slack":
            print(t("  api.slack.com/apps > uygulama oluştur > bot izinleri: chat:write ve channels:history (özel kanal için groups:history,\n"
                    "  DM için im:history) > kur. Kanal id'si C ile, DM id'si D ile başlar; senin id'n U ile (profil > ⋯ > Copy member ID).",
                    "  api.slack.com/apps > create app > bot scopes: chat:write and channels:history (groups:history for a private channel,\n"
                    "  im:history for a DM) > install. A channel id starts with C, a DM with D; yours with U (profile > ⋯ > Copy member ID)."))
        else:
            print(t("  discord.com/developers > uygulama > Bot: Message Content intent'i aç, botu sunucuna ekle. Id'ler için\n"
                    "  Ayarlar > Gelişmiş > Geliştirici Modu, sonra kanala ve kendine sağ tık > ID'yi Kopyala.",
                    "  discord.com/developers > application > Bot: turn on Message Content intent and add the bot to your server. For ids,\n"
                    "  Settings > Advanced > Developer Mode, then right-click the channel and yourself > Copy ID."))
        kanal = ask(t("  Kanal id'si", "  Channel id"), eski.get("channel_id", ""))
        sahip = ask(t("  Senin kullanıcı id'n", "  Your user id"), eski.get("owner_id", ""))
        env = eski.get("token_env") or f"PENTARCH_{ad.upper()}_TOKEN"
        if not read_env(SECRETS / "keys.env").get(env) or yes(t("  Kayıtlı token değiştirilsin mi?", "  Replace the saved token?")):
            tok = secret(t(f"  Bot token'ı (gizli, {env} olarak kaydedilir; boş geçer): ",
                           f"  Bot token (hidden, saved as {env}; empty skips): ")).strip()
            if ad == "slack" and tok and not tok.startswith("xoxb-"):
                print(t("  Bu bir bot token'ı değil (xoxb- ile başlamalı). Slack kapalı kalıyor.",
                        "  That isn't a bot token (it should start with xoxb-). Slack stays off."))
                continue
            if tok:
                koltuk.save_key(env, tok)
        on = bool(kanal and sahip and read_env(SECRETS / "keys.env").get(env))
        gw[ad] = {**eski, "enabled": on, "channel_id": kanal, "owner_id": sahip, "token_env": env}
        if not on:
            print(t(f"  {ad_tr} eksik bilgi yüzünden kapalı kaldı.", f"  {ad_tr} stays off: something was missing."))
    return gw


APPLICANT = (  # key, tr question, en question: what application forms ask again and again
    ("about", "Kendini ve deneyimini 2-4 cümleyle anlat (ne yapıyorsun, iş/staj, neyi iyi yapıyorsun, ne arıyorsun)",
     "Tell me about yourself and your experience in 2-4 sentences (what you do, jobs/internships, what you are good at, what you look for)"),
    ("full_name", "Ad soyad (formlarda yazılacak hâli)", "Full name (as forms should show it)"),
    ("email", "Başvurularda kullanılacak e-posta", "Email for applications"),
    ("phone", "Telefon (ülke koduyla)", "Phone (with country code)"),
    ("links", "Bağlantılar: LinkedIn, GitHub, portfolyo (virgülle)", "Links: LinkedIn, GitHub, portfolio (comma separated)"),
    ("education", "Eğitim: okul, bölüm, mezuniyet yılı (sürüyorsa beklenen)", "Education: school, degree, graduation year (expected if ongoing)"),
    ("current_employer", "Şu an çalıştığın yer (biten staj sayılmaz; yoksa boş)", "Where you work now (a finished internship does not count; empty if none)"),
    ("highlights", "Projeler dışında en güçlü 1-3 sonucun (açık kaynak, ödül, iş), sayı ya da linkle; projeleri birazdan tek tek soracağım",
     "Your 1-3 strongest results outside projects (open source, awards, jobs), with a number or a link; projects come next, one by one"),
    ("languages", "Konuştuğun diller ve seviyesi (virgülle; English C1, Türkçe ana dil gibi)",
     "Languages you speak and level (comma separated; like English C1, German B1)"),
    ("work_authorization", "Vizesiz çalışabildiğin ülkeler (başka yerde sponsor gerekir sayılır; hiç gerekmiyorsa 'her yer')",
     "Countries where you can work without a visa (elsewhere counts as needing sponsorship; 'anywhere' if you never need one)"),
    ("start_date", "En erken başlama tarihi ya da ihbar süresi", "Earliest start date or notice period"),
    ("salary", "Maaş beklentisi (tutar, para birimi; boş bırakılabilir)", "Salary expectation (amount, currency; may be empty)"),
    ("cv_path", "Hazır CV dosyanın yolu (yoksa boş)", "Path to your existing CV file (empty if none)"),
)


NO_SPONSOR = ["no visa sponsorship", "no sponsorship", "unable to sponsor", "not able to sponsor", "cannot sponsor",
              "do not sponsor", "does not sponsor", "will not sponsor"]  # skipped when you need a visa; no "without sponsorship", IMC writes it in a welcome line


ANYWHERE = re.compile(r"\s*(?:her ?yer|anywhere|everywhere|worldwide|tüm dünya)\b", re.I)
PROJECT = (("link", "link ya da kanıt (repo, demo, rapor; yoksa boş)", "link or evidence (repo, demo, report; empty if none)"),
           ("result", "tek ölçülebilir sonuç (sayı, test, kullanıcı ya da skor)", "one measurable result (a number, tests, users or a score)"),
           ("role", "senin payın (tek başına mı, takımda ne yaptın)", "your part (solo, or what you did in the team)"))
JOB = (("employer", "işveren", "employer"),
       ("dates", "tarihler (2019-2024 gibi)", "dates (like 2019-2024)"),
       ("result", "o işte en ölçülebilir sonucun (sayı, kişi, süre)", "your most measurable result there (a number, people, time)"))


def items_setup(old, fields, head, label, limit=5):
    """Up to `limit` entries asked one by one (projects, past jobs): what CV bullets are built from."""
    print(head)
    out = []
    for i in range(limit):
        o = old[i] if i < len(old) else {}
        name = ask("  " + t(f"{label[0]} {i + 1}", f"{label[1]} {i + 1}"), o.get("name", ""))
        if name.strip().lower() in ("", "geç", "gec", "skip", "-"):
            break
        out.append({"name": name, **{k: ask("    " + t(tr, en), o.get(k, "")) for k, tr, en in fields}})
    return out


def projects_setup(old):
    return items_setup(old, PROJECT, t("  Projeler: CV maddeleri bunlardan çıkar. En fazla 5; bitirmek için adı boş bırak ya da 'geç' yaz.",
                                       "  Projects: CV bullets are built from these. Up to 5; leave the name empty or type 'skip' to stop."),
                       ("Proje adı", "Project name"))


def jobs_setup(old):
    """Past jobs, newest first: a career changer's strongest evidence, and the CV's Experience section."""
    return items_setup(old, JOB, t("  Geçmiş işler (stajlar dahil, en yenisi önce). Bitirmek için unvanı boş bırak.",
                                   "  Past jobs (internships too, newest first). Leave the title empty to stop."),
                       ("Unvan", "Job title"))


def applicant_setup(cur, city="", locs=()):
    """"Tell me about yourself": what application forms ask, asked once and kept in tracker/profile.json (gitignored,
    stays on this machine). The assistant fills forms from it and still asks before every submit (rules: outward step).
    city, relocate and needs_sponsorship come from earlier answers instead of being asked again; older profiles that
    kept experience, relocate or needs_sponsorship as their own answers still load, and those keys are still written."""
    print(t("\nKendini anlat: başvuru formlarının hep sorduğu bilgiler. Bir kez cevapla; asistan formları bunlarla doldurur,\n"
            "  göndermeden önce her seferinde sana sorar. Bilmediğini boş geç, sonra tracker/profile.json'dan düzeltirsin.",
            "\nAbout you: what application forms always ask. Answer once; the assistant fills forms from it and asks you\n"
            "  before every submit. Skip what you don't know; fix it later in tracker/profile.json."))
    if not yes(t("Şimdi doldurulsun mu?", "Fill it in now?"), not cur):
        return cur
    out = {"_": "Form answers. Filled by setup.py; the assistant reads them for applications and never submits without asking."}
    for key, tr_q, en_q in APPLICANT:
        old = cur.get(key, "")
        out[key] = ask("  " + t(tr_q, en_q), ", ".join(old) if isinstance(old, list) else str(old))
    for key in ("links", "languages"):
        out[key] = [x.strip() for x in out[key].split(",") if x.strip()]
    out["jobs"] = jobs_setup(cur.get("jobs") or [])
    out["projects"] = projects_setup(cur.get("projects") or [])
    wa = out["work_authorization"].strip()
    guess = cur.get("needs_sponsorship") == "yes" if not wa else not ANYWHERE.match(wa)
    visa = yes(t("  İş aradığın yerlerde çalışmak için vize sponsoru gerekiyor mu?",
                 "  Do you need visa sponsorship to work where you're looking?"), guess)
    out.update(city=city or cur.get("city", ""), experience=cur.get("experience") or out["about"],
               needs_sponsorship="yes" if visa else "no",
               relocate="yes" if any(l.lower().startswith("relocation") for l in locs) else cur.get("relocate") or "no")
    out["cv_path"] = out["cv_path"].strip().strip("\"'")  # Windows "Copy as path" adds quotes
    if out["cv_path"] and not Path(out["cv_path"]).expanduser().exists():
        print(t(f"  ! {out['cv_path']} bulunamadı; yolu sonra düzelt.", f"  ! {out['cv_path']} not found; fix the path later."))
    return out


def _fill(text, notes):
    """Placeholders in the shipped skills and agents: tool paths, the notes folder and the home folder."""
    return (text.replace("skills/linkedin/li.py", f'"{REPO / "skills" / "linkedin" / "li.py"}"')
            .replace("skills/cv/cv.py", f'"{REPO / "skills" / "cv" / "cv.py"}"')
            .replace("tracker/apply.py", f'"{REPO / "tracker" / "apply.py"}"')
            .replace("{{NOTES}}", str(Path(notes).expanduser())).replace("{{HOME}}", str(HOME)))


SHIPPED = HOME / "kurulan_beceriler.json"  # hash of every skill/agent file setup wrote, to tell an old copy from an edit


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _old_version(src, cur, notes):
    """Installs from before the hash record: is cur exactly what some earlier version of src would have installed?"""
    git, rel = shutil.which("git"), src.relative_to(REPO).as_posix()
    if not git:
        return False
    revs = subprocess.run([git, "-C", str(REPO), "rev-list", "HEAD", "--", rel], capture_output=True, text=True).stdout.split()
    for h in revs:
        old = subprocess.run([git, "-C", str(REPO), "show", f"{h}:{rel}"], capture_output=True, encoding="utf-8", errors="replace").stdout
        if _fill(old.replace("\r\n", "\n"), notes) == cur:
            return True
    return False


def _copy_new(src, dst, notes, shipped):
    """Copy one file unless the user has their own there: a file setup never wrote, or one they edited after.
    A copy setup wrote and nobody touched is replaced, so a newer version of the skill arrives. False when left alone."""
    new = _fill(src.read_text(encoding="utf-8"), notes)
    if dst.exists():
        cur = dst.read_text(encoding="utf-8")
        if cur != new and _sha(cur) != shipped.get(str(dst)) and not (str(dst) not in shipped and _old_version(src, cur, notes)):
            return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(new, encoding="utf-8")
    shipped[str(dst)] = _sha(new)
    return True


def skills_setup(cli, notes="~/notes", ask_first=True):
    """Repo skills (skills/<name>/SKILL.md): a pointer in <home>/beceriler so memory search attaches them, and for
    Claude Code a copy under ~/.claude/skills so /<name> works in the chat too, plus the subagents in agents/
    (the konsey council and log-avcisi) under ~/.claude/agents. A skill or agent the user already has under the
    same name is never overwritten."""
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
    if cli == "claude" and (not ask_first or yes(t(f"Beceriler Claude Code'a da kopyalansın mı ({names})?",
                                                   f"Copy the skills into Claude Code too ({names})?"), True)):
        target = Path.home() / ".claude" / "skills"
        kept = []
        shipped = json.loads(SHIPPED.read_text(encoding="utf-8")) if SHIPPED.exists() else {}
        for d in dirs:
            # SKILL.md decides: if the user has their own skill by this name, the whole folder is left alone
            if not _copy_new(d / "SKILL.md", target / d.name / "SKILL.md", notes, shipped):
                kept.append(f"skills/{d.name}")
                continue
            for f in d.rglob("*"):
                if f.is_file() and f.name != "SKILL.md" and "__pycache__" not in f.parts:
                    out = target / d.name / f.relative_to(d)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, out)
        agents = REPO / "agents"
        for f in sorted(agents.glob("*.md")) if agents.is_dir() else []:
            if not _copy_new(f, Path.home() / ".claude" / "agents" / f.name, notes, shipped):
                kept.append(f"agents/{f.name}")
        SHIPPED.write_text(json.dumps(shipped, indent=1), encoding="utf-8")
        print(t(f"  Kopyalandı: {target} ve ~/.claude/agents", f"  Copied to: {target} and ~/.claude/agents"))
        if kept:
            print(t("  Dokunulmadı (aynı adla senin kendi ya da düzenlediğin dosyan var): ",
                    "  Left alone (you have your own or an edited one by that name): ")
                  + ", ".join(kept))
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


def termux_boot_script(py, app, log):
    """Termux:Boot script. A restart loop, so a crash or Android's process killer doesn't leave it dead until the next
    reboot. `py` is the venv's Python (install.sh's packages live there, not in Termux's own python)."""
    loop = f"while true; do {shlex.quote(str(py))} -I {shlex.quote(str(app))} --quiet; sleep 30; done"
    return ("#!/data/data/com.termux/files/usr/bin/sh\ntermux-wake-lock\n"
            f"PENTARCH_SUPERVISED=1 nohup sh -c {shlex.quote(loop)} >> {shlex.quote(str(log))} 2>&1 &\n")


def launchd_plist(py, app, path_env, log, home=HOME):
    # KeepAlive stays unconditional: an update restart exits 0 on purpose and expects launchd to start it again.
    # ThrottleInterval keeps a crash loop (bad token, port busy) from respawning every 10 s.
    x = lambda s: xml_escape(str(s))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.pentarch</string>
<key>ProgramArguments</key><array><string>{x(py)}</string><string>-I</string><string>{x(app)}</string><string>--quiet</string></array>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>{x(path_env)}</string><key>PENTARCH_SUPERVISED</key><string>1</string>
<key>PENTARCH_HOME</key><string>{x(home)}</string></dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>60</integer>
<key>StandardOutPath</key><string>{x(log)}</string><key>StandardErrorPath</key><string>{x(log)}</string>
</dict></plist>
"""


def systemd_unit(py, app, path_env, home=HOME):
    # systemd splits ExecStart on spaces unless quoted, and reads % as a specifier
    q = lambda s: '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
    return f"""[Unit]
Description=Pentarch assistant
Wants=network-online.target
After=network-online.target

[Service]
ExecStart={q(py)} -I {q(app)} --quiet
Environment={q("PATH=" + path_env)}
Environment=PENTARCH_SUPERVISED=1
Environment={q("PENTARCH_HOME=" + str(home))}
NoNewPrivileges=yes
UMask=0077
PrivateTmp=yes
Restart=always
RestartSec=30
RestartPreventExitStatus=78

[Install]
WantedBy=default.target
"""


def service_setup():
    """Linux: systemd --user unit. macOS: launchd agent. Both restart Pentarch after it exits (updates, crashes)."""
    py, app = Path(sys.executable), APP / "pentarch.py"
    path_env = os.environ.get("PATH", "")  # the agent CLI (node, claude, ...) must be found from a service too
    if os.environ.get("PENTARCH_DOCKER"):  # the container's restart policy is the service
        print(t("  Docker'da: `docker compose up -d` başlatır, kapanınca ya da güncellenince Docker yeniden açar.",
                "  In Docker: `docker compose up -d` starts it, and Docker brings it back after a restart or crash."))
        return True
    if sys.platform == "darwin":
        if not opt(t("Mac açılınca Pentarch başlasın mı?", "Start Pentarch when you log in to this Mac?"), True):
            return False
        plist = Path.home() / "Library/LaunchAgents/com.pentarch.plist"
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(launchd_plist(py, app, path_env, HOME / "service.log"), encoding="utf-8")
        print(t("  macOS birazdan 'Arka Plan Öğesi Eklendi' diye bir bildirim gösterebilir ve adını Python koyar: o, Pentarch."
                " Sistem Ayarları > Genel > Giriş Öğeleri'nden kapatırsan Pentarch durur.",
                "  macOS may now show a 'Background Items Added' notice that names Python: that is Pentarch."
                " Switching it off in System Settings > General > Login Items stops Pentarch."))
        domain = f"gui/{os.getuid()}"  # load/unload are deprecated and fail quietly on recent macOS
        subprocess.run(["launchctl", "bootout", f"{domain}/com.pentarch"], capture_output=True)
        ok = subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True).returncode == 0
        print(t("  Başladı; Mac'e girişte kendiliğinden açılır. PATH bu anki haliyle yazıldı; ajan CLI'ını taşırsan"
                " kurulumu yeniden çalıştır." if ok else f"  Dosya yazıldı ({plist}); `launchctl bootstrap {domain}` çalışmadı.",
                "  Started; it will launch at login. PATH was saved as it is now; if you move the agent CLI, run setup"
                " again." if ok else f"  File written ({plist}); `launchctl bootstrap {domain}` failed."))
        return ok
    if not shutil.which("systemctl"):
        print(t("  systemd yok; otomatik başlatma atlandı. Elle: python -I " + str(app),
                "  No systemd here, so autostart is skipped. Run it by hand: python -I " + str(app)))
        return False
    if not opt(t("Bilgisayar açılınca Pentarch başlasın mı (systemd kullanıcı servisi)?",
                 "Start Pentarch at boot (systemd user service)?"), True):
        return False
    unit = Path.home() / ".config/systemd/user/pentarch.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(systemd_unit(py, app, path_env), encoding="utf-8")
    run = lambda *a: subprocess.run(["systemctl", "--user", *a], capture_output=True).returncode == 0
    ok = run("daemon-reload") and run("enable", "--now", "pentarch.service")
    user = os.environ.get("USER", "")
    subprocess.run(["loginctl", "enable-linger", user], capture_output=True)  # run without a login session
    linger = subprocess.run(["loginctl", "show-user", user, "--property=Linger"], capture_output=True,
                            text=True).stdout.strip() == "Linger=yes"  # without polkit or root the call above fails quietly
    print(t("  Başladı. Durum: systemctl --user status pentarch" if ok
            else f"  Dosya yazıldı ({unit}); servis başlamadı, `systemctl --user status pentarch` bak.",
            "  Started. Check: systemctl --user status pentarch" if ok
            else f"  Unit written ({unit}); it did not start. See `systemctl --user status pentarch`."))
    if ok:
        print(t("  Bilgisayar açılınca, sen giriş yapmadan da çalışır." if linger else
                f"  Şimdilik yalnız sen giriş yapınca çalışır. Açılışta da çalışsın diye bir kez: sudo loginctl enable-linger {user}",
                "  It runs at boot, even before you log in." if linger else
                f"  For now it only runs while you are logged in. To run it at boot, once: sudo loginctl enable-linger {user}"))
    return ok


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
    if not opt(t("\n  Wiki'nin geçmişi GitHub'daki özel (private) bir repoya yedeklensin mi?",
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


def upgrade():
    """After a git pull: the same skill and agent install as setup, without questions. Files the user changed stay."""
    global TR
    if not CONFIG.exists():
        sys.exit("No pentarch.json yet; run python setup.py first.")
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    TR = cfg.get("lang") == "tr"
    skills_setup(cfg.get("agent", {}).get("cli", "claude"), cfg.get("notes_dir", "~/notes"), ask_first=False)
    added = rules_upgrade(cfg)
    if added:
        print(t(f"kurallar.md'ye yeni kurallar eklendi: {', '.join(added)}", f"New rules added to kurallar.md: {', '.join(added)}"))


RULE = re.compile(r"^(\d+[a-z]?)\. ")
EK = re.compile(r"(\{\{(?:OWNER|NAME)\}\})'([a-zçğıöşü]+)")


def ek(ad, son):
    """Turkish templates write suffixes for a name like Rızgar ('ın, 'a, 'dan, 'sın). Bend them to the real name's
    vowels and ending: Ayşe'nin, Ayşe'ye, Ülkü'yle, Zeynep'ten. English "'s" passes through unchanged."""
    ad_k = ad.replace("I", "ı").replace("İ", "i").lower()
    sesli = [c for c in ad_k if c in "aeıioöuü"]
    if not sesli or son == "s":
        return son
    v = sesli[-1]
    ince, yuvarlak = v in "eiöü", v in "oöuü"
    dort = ("ü" if yuvarlak else "i") if ince else ("u" if yuvarlak else "ı")
    son = "".join("e" if c == "a" and ince else dort if c == "ı" else c for c in son)
    if ad_k[-1] in "aeıioöuü" and son[0] in "aeıioöuü":
        son = ("n" if son[0] in "ıiuü" and son[1:2] == "n" else "y") + son
    elif son[0] == "l" and ad_k[-1] in "aeıioöuü":
        son = "y" + son  # ile: Ayşe'yle
    elif son[0] == "d" and ad_k[-1] in "çfhkpsşt":
        son = "t" + son[1:]
    return son


def doldur(text, fill):
    text = EK.sub(lambda m: m.group(1) + "'" + ek(fill.get(m.group(1), ""), m.group(2)) if fill.get(m.group(1)) else m.group(0), text)
    for k, v in fill.items():
        text = text.replace(k, v)
    return text


def rules_upgrade(cfg):
    """Numbered rules the template has and <home>/kurallar.md lacks go in after the rule before them. Rules already
    there stay as the user left them. Returns the numbers added; a backup goes to kurallar.md.bak first."""
    dst, src = HOME / "kurallar.md", REPO / "templates" / cfg.get("lang", "en") / "kurallar.md"
    if not dst.exists() or not src.exists():
        return []
    fill = {"{{APP}}": APP.as_posix(), "{{HOME}}": HOME.as_posix(),
            "{{NOTES}}": Path(cfg.get("notes_dir", "~/notes")).expanduser().as_posix(),
            "{{OWNER}}": cfg.get("owner", ""), "{{NAME}}": cfg.get("name", "")}
    blocks, cur = [], None  # template rules with their indented continuation lines
    for line in src.read_text(encoding="utf-8").splitlines():
        if m := RULE.match(line):
            cur = [m.group(1), [line]]
            blocks.append(cur)
        elif cur and line.startswith("  ") and line.strip():
            cur[1].append(line)
        else:
            cur = None
    old = dst.read_text(encoding="utf-8")
    lines = old.splitlines()
    have = {m.group(1) for line in lines if (m := RULE.match(line))}
    added, prev = [], None
    for no, body in blocks:
        if no not in have:
            text = doldur("\n".join(body), fill)
            if "{{" not in text:  # a placeholder only setup can fill: leave that rule for setup.py --force
                at = len(lines)
                if prev:
                    at = next(i for i, line in enumerate(lines) if (m := RULE.match(line)) and m.group(1) == prev) + 1
                    while at < len(lines) and lines[at].startswith("  ") and lines[at].strip():
                        at += 1
                lines[at:at] = text.split("\n")
                have.add(no)
                added.append(no)
        if no in have:
            prev = no
    if added:
        (HOME / "kurallar.md.bak").write_text(old, encoding="utf-8")
        dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return added


def permission_setup(agent):
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
    return perm, bypass_ok


def main():
    global TR
    if os.name != "nt":
        os.umask(0o077)  # tokens and keys are written before their chmod; nothing setup makes needs other users
    if {"-h", "--help"} & set(sys.argv[1:]):
        print("python setup.py            guided setup (asks before it changes anything)\n"
              "python setup.py --upgrade  pull new rules and files into an existing install\n"
              f"Runtime home: {HOME} (set PENTARCH_HOME to move it)")
        return
    if "--upgrade" in sys.argv:
        return upgrade()
    old = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    agent = old.get("agent", {})
    print(f"Pentarch setup. Home folder: {HOME}")
    print("Enter = the default in [brackets] / Enter = [köşeli parantezdeki] varsayılan\n")

    global QUICK
    pick = ask("Language / Dil:  1 = English, 2 = Türkçe, 3 = other / otro / autre (setup in English)",
               "3" if old.get("reply_lang") else {"tr": "2"}.get(old.get("lang"), "1"), ("1", "2", "3", "en", "tr"))
    lang = {"1": "en", "2": "tr", "3": "en"}.get(pick, pick)
    reply_lang = ""
    if pick == "3":  # the agent writes in any language; the few fixed messages the code sends stay in English
        reply_lang = ask("Which language should it write to you in? (e.g. Español, Deutsch, Português)",
                         old.get("reply_lang", "")).strip()
    TR = lang == "tr"
    print(t("Hızlı kurulum yalnızca gerekenleri sorar (adın, ne iş yaptığın, hangi yapay zekâ hesabını kullanacağı, Telegram, iş arayıp aramadığın);\n"
            "gerisi hazır ayarla gelir. Emin değilsen Enter'a bas. Ayrıntılı kurulum ince ayarları da sorar; sonra istediğin an yeniden çalıştırabilirsin.",
            "Quick setup asks only what's needed (names, what you do, which AI account it uses, Telegram, whether you're job hunting);\n"
            "the rest takes defaults. Not sure? Press Enter. Detailed setup also asks the fine-tuning questions; you can re-run it any time."))
    QUICK = yes(t("Hızlı kurulum?", "Quick setup?"), True)
    STEP[1] = 6 if QUICK else 8
    step("Temel bilgiler", "The basics")
    preflight()
    owner = ask(t("Senin adın", "Your name"), old.get("owner", ""))
    name = ask(t("Asistanın adı", "Assistant name"), old.get("name", "Pentarch"))
    about = ask(t("Ne iş yapıyorsun? Bir cümle, boş geçebilirsin (örn. fırın işletiyorum / bilgisayar mühendisliği 3. sınıfım)",
                  "What do you do? One sentence, Enter to skip (e.g. I run a bakery / I'm a 3rd-year CS student)"), old.get("about", ""))
    notes = old.get("notes_dir", "~/storage/shared/Documents/wiki" if TERMUX else "~/notes")
    if not QUICK:
        notes = ask(t("Not klasörü (asistanın wiki'si, markdown)", "Notes folder (the assistant's wiki, markdown)"), notes)

    step("Ajan (asistanın beyni)", "Agent (the assistant's brain)")
    HOME.mkdir(parents=True, exist_ok=True)  # agent_test runs inside it
    found = [c for c in CLIS if shutil.which(c)]
    print(t("Asistan düşünmek için senin yapay zekâ hesabını kullanan bir program çalıştırır. Emin değilsen: Claude aboneliğin varsa claude,\n"
            "yoksa gemini (Google hesabıyla ücretsiz kota). codex = ChatGPT hesabı, opencode = kendi anahtarın.\n"
            "api = hiç program yok: kendi modelin (Ollama, LM Studio, sunucu) ya da OpenAI uyumlu herhangi bir servis.",
            "The assistant runs a small program that uses your own AI account to think. Not sure? claude if you pay for Claude,\n"
            "otherwise gemini (free quota with a Google account). codex = ChatGPT account, opencode = your own key.\n"
            "api = no program at all: your own model (Ollama, LM Studio, a server) or any OpenAI-compatible service."))
    print(t("Bu bilgisayarda bulunan: ", "Found on this computer: ") + (", ".join(found) or "-"))
    guess = agent.get("cli") or (found[0] if found else None)
    picked = not guess
    if picked:
        print(t("Hangi yapay zekâ aboneliğin var?  1 = Claude (ücretli), 2 = ChatGPT Plus/Pro (ücretli), 3 = Google (ücretsiz de olur), "
                "4 = kendi API anahtarım, 5 = hiçbiri, kendi modelim (Ollama, LM Studio, sunucu)",
                "Which AI subscription do you have?  1 = Claude (paid), 2 = ChatGPT Plus/Pro (paid), 3 = Google (free works too), "
                "4 = my own API key, 5 = none, my own model (Ollama, LM Studio, a server)"))
        guess = {"1": "claude", "2": "codex", "3": "gemini", "4": "opencode", "5": "api"}[
            ask(t("Abonelik", "Subscription"), "3", ("1", "2", "3", "4", "5"))]
    cli = guess if picked else ask(t("Ajan programı", "Agent CLI"), guess, (*CLIS, "api"))
    if not cli_setup(cli):
        print(t(f"  {cli} hazır değil; kurulum sürüyor, sonunda ne kaldığını yazacağım.",
                f"  {cli} isn't ready; setup goes on and lists what's left at the end."))
    same = agent.get("cli") == cli
    models = {"claude": ("sonnet", "opus", "haiku")}.get(cli, ("", "", ""))
    fast, deep, light = ((agent.get("fast_model", models[0]), agent.get("deep_model", models[1]), agent.get("light_model", models[2]))
                         if same else models)
    if not QUICK:
        print(t("Üç model: günlük = sıradan mesajlar, derin = zor işler, hafif = küçük arka plan işleri. Emin değilsen Enter.",
                "Three models: everyday = ordinary messages, deep = hard work, light = small background jobs. Not sure? Enter."))
        if cli != "claude":
            print(t("  Boş bırakırsan CLI'ın kendi varsayılanı kullanılır.", "  Empty means the CLI's own default."))
        fast = ask(t("Günlük model", "Everyday model"), fast)
        deep = ask(t("Derin model", "Deep model"), deep)
        light = ask(t("Hafif model", "Light model"), light)
    perm = agent.get("permission_mode", "acceptEdits")
    bypass_ok = bool(agent.get("bypass_confirmed")) and perm == "bypassPermissions"
    if not QUICK:
        perm, bypass_ok = permission_setup(agent)

    plan = old.get("plan", "max")
    if cli == "claude":
        print(t("Hangi Claude aboneliğin var? pro = otomatik işler az ve hafif koşar, kendi sohbetlerine kota kalır;\n"
                "               max = her şey tam; api = abonelik yok, kullandıkça para ödersin (ANTHROPIC_API_KEY).",
                "Which Claude subscription do you have? pro = automatic jobs run lean and rarely, so your own chats keep their quota;\n"
                "                  max = everything full; api = no subscription, you pay per use (ANTHROPIC_API_KEY)."))
        plan = ask(t("Plan", "Plan"), old.get("plan", "max" if old else "pro"), ("pro", "max", "api"))
        if plan == "api" and not koltuk.has_key("ANTHROPIC_API_KEY"):
            k = anahtar.ask("anthropic", t, yes, secret, "ANTHROPIC_API_KEY")
            if k:
                koltuk.save_key("ANTHROPIC_API_KEY", k)

    SECRETS.mkdir(parents=True, exist_ok=True)
    step("Telegram (telefondan konuşmak için)", "Telegram (to chat from your phone)")
    telegram_setup()
    step("Ücretsiz anahtarlar", "Free keys")
    api = free_keys_setup(old.get("chat_api") or {"base_url": "", "model": "", "key_env": "PENTARCH_CHAT_KEY"})
    if cli == "api":  # the brain itself: asked even in quick mode
        if QUICK:
            STEP[1] += 1
        step("Beyin servisi", "Brain service")
        api = chat_api_setup(api, beyin=True)
    if not QUICK:
        step("Ek servis ve konsey", "Extra service and council")
        if cli != "api":
            api = chat_api_setup(api)
        print(t("Konsey: zor bir soruda birkaç farklı modele sorup cevapları karşılaştırır. Her koltuk bir model.",
                "Council: on a hard question it asks several different models and compares the answers. Each seat is one model."))
        council_setup()
    job_boards, mcp_servers = old.get("job_boards") or {}, old.get("mcp_servers", {})
    if not QUICK:
        step("Kariyer takibi ve MCP", "Career tracking and MCP")
        job_boards = career_setup(old, lang)
        if cli == "claude":
            print(t("MCP: Claude'a ek araç bağlayan sunucular (takvim, tarayıcı gibi). Bilmiyorsan hayır de.",
                    "MCP: servers that give Claude extra tools (calendar, browser and so on). If unsure, say no."))
            mcp_servers = mcp_setup(old)
    elif yes(t("\nİş ya da staj arıyor musun? Evet dersen her sabah ilanları tarar, başvuru paketlerini hazırlar ve onayına sunar.",
               "\nAre you looking for a job or internship? If yes, it scans postings every morning, drafts application packages and asks before sending."),
             (REPO / "tracker" / "profile.json").exists()):
        job_boards = career_setup(old, lang, asked=True)
    gateways, mail_on = mail_setup(old)
    if not QUICK or not (SECRETS / "telegram.txt").exists():  # quick setup without Telegram still needs some door
        gateways = doors_setup(gateways)
    step("Kurulum", "Installing")

    off = set(old.get("jobs_off", ["guncelle", "insa", "posta"]))
    if mail_on:
        off.discard("posta")  # the inbox was just connected, so the mail check starts on
    if plan == "pro" and old.get("plan") != "pro":
        off.add("kesif")
        print(t("  Pro: haftalık keşif turu (kesif) kapatıldı; panelden açabilirsin.",
                "  Pro: the weekly discovery round (kesif) is off; you can turn it on in the panel."))
    print(t("\nGece kendini geliştirme turu ilk başta kapalı; panelden açabilirsin (Ayarlar > Çalışmasın)." if QUICK else
            "\nİki rutin ilk başta kapalı; istersen şimdi aç, sonra panelden de değiştirebilirsin (Ayarlar > Çalışmasın).",
            "\nThe nightly self-build round starts off; turn it on in the panel (Settings > Disabled routines)." if QUICK else
            "\nTwo routines start off; turn them on now if you like, or later in the panel (Settings > Disabled routines)."))
    for job, tr_q, en_q in (("insa", "Gece kendini geliştirme turu (insa) açılsın mı?", "Turn on the nightly self-build round (insa)?"),
                            ("posta", "Posta kontrolü (posta) açılsın mı?", "Turn on the mail check (posta)?")):
        if QUICK or (job == "posta" and mail_on):  # quick setup keeps the defaults (README: everything else takes its default)
            continue
        if opt(t(tr_q, en_q), job not in off):
            off.discard(job)
        else:
            off.add(job)
    print(t("  Otomatik güncelleme (sen açmazsan kapalı): her gece 05:10'da GitHub'daki yeni sürümü çeker (yalnız klasörde senin değişikliğin yoksa),\n"
            "  Pentarch boşta kalınca kendini yeniden başlatır ve sana tek satır yazar.",
            "  Auto-update (off unless you turn it on): every night at 05:10 pulls the new version from GitHub (only when you have no local changes),\n"
            "  Pentarch restarts itself once idle and tells you in one line."))
    if opt(t("Otomatik güncelleme (guncelle) açılsın mı?", "Turn on auto-update (guncelle)?"), "guncelle" not in off):
        off.discard("guncelle")
    else:
        off.add("guncelle")

    cfg = {**old, "owner": owner or "Owner", "name": name or "Pentarch", "about": about, "lang": lang, "reply_lang": reply_lang, "notes_dir": notes,
           "agent": {**agent, "cli": cli, "fast_model": fast, "deep_model": deep, "light_model": light,
                     "permission_mode": perm, "bypass_confirmed": bypass_ok},
           "plan": plan, "chat_api": api, "jobs_off": sorted(off), "job_boards": job_boards, "mcp_servers": mcp_servers,
           "gateways": gateways,
           "council": koltuk.seats()}  # koltuk.add wrote seats to the file during setup; `old` predates them

    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    CONFIG.chmod(0o600)
    panel_settings = HOME / "ayarlar.json"  # the panel's own switches, once Pentarch has run
    if panel_settings.exists():
        a = json.loads(panel_settings.read_text(encoding="utf-8"))
        a["kapali_isler"] = sorted(set(a.get("kapali_isler", [])) - {"insa", "posta", "guncelle"} | off)
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
        if opt(t("  Wiki iskeleti kurulsun mu?", "  Set up the wiki skeleton?"), True):
            sys.path.insert(0, str(APP))
            import wiki
            made = wiki.kur(notes, cfg["owner"], cfg["name"], lang)
            print(t(f"  Kuruldu: {', '.join(made)}", f"  Created: {', '.join(made)}"))
    small_business_setup(Path(notes).expanduser(), lang)
    wiki_backup(Path(notes).expanduser())

    fill = {"{{APP}}": APP.as_posix(), "{{HOME}}": HOME.as_posix(), "{{NOTES}}": Path(notes).expanduser().as_posix(),
            "{{OWNER}}": cfg["owner"], "{{NAME}}": cfg["name"],
            "{{WHO}}": cfg.get("about") or t("(bir cümle: ne iş yapıyorsun, nerede, hangi aşamadasın)", "(one sentence: what you do, where, at what stage)"),
            "{{APPLY}}": t("(başvuru bilgisi yok; setup.py'yi yeniden çalıştır)", "(no applicant details yet; run setup.py again)")}
    fill.update({"{{GOALS}}": t("(önümüzdeki aylar için 2-3 somut hedef, varsa son tarihleriyle)", "(2-3 concrete goals for the coming months, with deadlines if any)"),
                 "{{INTERESTS}}": t("(izlemem gereken konular, teknolojiler, fırsat türleri)", "(topics, technologies and kinds of opportunities to watch for)")})
    pf = REPO / "tracker" / "profile.json"
    if pf.exists():  # the career answers also seed the agent's profile.md
        prof = json.loads(pf.read_text(encoding="utf-8"))
        fill.update({"{{GOALS}}": t("şu rollerde iş bulmak: ", "find a role as ") + ", ".join(prof.get("target_roles") or []) +
                     (" (" + ", ".join(prof.get("locations") or []) + ")" if prof.get("locations") else ""),
                     "{{INTERESTS}}": ", ".join((prof.get("skills") or []) + (prof.get("target_roles") or []))})
        if (ap := prof.get("applicant") or {}).get("about"):
            fill["{{WHO}}"] = ap["about"]
        if any(v for k, v in ap.items() if k != "_"):
            fill["{{APPLY}}"] = t(f"form cevapları {pf} içindeki applicant bölümünde (iletişim, eğitim, çalışma izni, maaş, CV yolu); "
                                  "formu onlarla doldur, eksik alanı uydurma, sor; göndermeden önce her seferinde onay al",
                                  f"form answers are in the applicant block of {pf} (contact, education, work permit, salary, CV path); "
                                  "fill forms from it, ask instead of inventing a missing field, get approval before every submit")
    kept = []
    for src in sorted((REPO / "templates" / lang).iterdir()):
        dst = HOME / src.name
        if dst.exists() and not FORCE:
            kept.append(src.name)
            continue
        dst.write_text(doldur(src.read_text(encoding="utf-8"), fill), encoding="utf-8")
    if kept:
        print(t(f"Olduğu gibi kaldı: {', '.join(kept)} (--force üstüne yazar)", f"Kept existing: {', '.join(kept)} (--force overwrites)"))
    (HOME / "v2.on").write_text("", encoding="utf-8") if cli == "claude" else (HOME / "v2.on").unlink(missing_ok=True)
    if QUICK and cli == "claude":
        print(t("Beceriler ve alt ajanlar ~/.claude klasörüne kopyalanıyor (kendi düzenlediklerine dokunulmaz).",
                "Copying the skills and sub-agents into ~/.claude (anything you edited yourself is left alone)."))
    skills_setup(cli, cfg["notes_dir"], not QUICK)

    # asked even in quick setup: 300 MB on a metered or slow line is not something to do unasked.
    # faster-whisper needs wheels Termux doesn't have; only the small spoken-reply package goes there
    pkgs = ["edge-tts>=6.1"]
    groq_env = PRESETS["groq"][1]
    if koltuk.has_key(groq_env) and yes(t(
            "\nGroq anahtarın var: sesli mesajlar Groq'ta yazıya çevrilsin mi? Hızlıdır ve kurulum gerektirmez, ama ses kaydı Groq'a gider",
            "\nYou have a Groq key: turn voice messages into text on Groq? Fast and nothing to install, but the recording goes to Groq"), TERMUX):
        conf = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
        conf.setdefault("whisper", {})["groq_key_env"] = groq_env
        CONFIG.write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")
    elif TERMUX:
        print(t("  Telefonda sesli mesajı yazıya çevirmek için ücretsiz bir Groq anahtarı gerekir (setup'ı yeniden çalıştırıp ekleyebilirsin);"
                " o zamana kadar yazarak konuş.",
                "  On a phone, voice messages need a free Groq key (rerun setup to add one); until then, type."))
    if not TERMUX and yes(t("\nSesli mesajlarını bu bilgisayarda yazıya çevirmek için paket kurulsun mu? Yaklaşık 300 MB indirir, "
                            "birkaç dakika sürer. Hayır dersen sesli mesajlar anlaşılmaz; sonra `pip install faster-whisper` ile kurabilirsin",
                            "\nInstall the package that turns your voice messages into text on this computer? Downloads about 300 MB "
                            "and takes a few minutes. Say no and voice messages won't be understood; `pip install faster-whisper` adds it later"), True):
        pkgs = ["-r", str(REPO / "requirements.txt")]
    if subprocess.run([sys.executable, "-m", "pip", "install", *pkgs]).returncode:
        print(t("  Paket kurulumu başarısız oldu; sesli özellikler çalışmaz, gerisi çalışır.",
                "  Package install failed; voice features won't work, everything else will."))

    if TERMUX:
        boot = Path.home() / ".termux" / "boot"
        if opt(t("Telefon açılınca Pentarch başlasın mı (Termux:Boot uygulaması gerekir)?",
                 "Start Pentarch when the phone boots (needs the Termux:Boot app)?"), True):
            boot.mkdir(parents=True, exist_ok=True)
            f = boot / "pentarch.sh"
            f.write_text(termux_boot_script(sys.executable, APP / "pentarch.py", HOME / "termux.log"), encoding="utf-8")
            f.chmod(0o755)
        print(t("  Telefonda: Termux'u pil optimizasyonundan çıkar (Ayarlar > Uygulamalar > Termux > Pil > Kısıtlama yok),"
                "\n  yoksa Android gece süreci öldürür. Android 14+: Geliştirici seçenekleri > 'Alt süreç kısıtlamalarını devre dışı bırak'"
                "\n  aç. Android 12-13'te bu ayar yok; bilgisayarsız yolu: Geliştirici seçenekleri > Kablosuz hata ayıklama'yı aç,"
                "\n  Termux'ta `pkg install android-tools`, ekrandaki eşleştirme koduyla `adb pair` ve `adb connect`, sonra"
                "\n  `adb shell device_config put activity_manager max_phantom_processes 2147483647`."
                "\n  Termux:Boot uygulamasını bir kere aç. Asistan telefonu uyanık tutar (wake lock); pil biraz daha hızlı biter."
                "\n  Wiki'yi Obsidian ile açmak için klasör: " + notes,
                "  On the phone: take Termux out of battery optimisation (Settings > Apps > Termux > Battery > Unrestricted),"
                "\n  or Android kills it at night. Android 14+: Developer options > 'Disable child process restrictions'."
                "\n  Android 12-13 lack that switch; without a computer: Developer options > turn on Wireless debugging,"
                "\n  in Termux `pkg install android-tools`, `adb pair` and `adb connect` with the code on screen, then"
                "\n  `adb shell device_config put activity_manager max_phantom_processes 2147483647`."
                "\n  Open the Termux:Boot app once. The assistant holds a wake lock, so the battery drains a bit faster."
                "\n  To read the wiki in Obsidian, open this folder: " + notes))
        if not (Path.home() / "storage").exists():
            print(t("  UYARI: önce `termux-setup-storage` çalıştır, yoksa wiki Obsidian'ın göremediği bir klasörde kalır.",
                    "  WARNING: run `termux-setup-storage` first, or the wiki lands where Obsidian can't see it."))

    if os.name == "nt":
        icon = REPO / "assets" / "pentarch.ico"
        appdata = Path(os.environ["APPDATA"]) / "Microsoft/Windows"
        if QUICK:
            print(t("Windows açılışına ve masaüstüne Pentarch kısayolu ekleniyor.", "Adding Pentarch shortcuts to Windows startup and the desktop."))
        if opt(t("Windows açılınca Pentarch başlasın mı?", "Start Pentarch when Windows starts?"), True):
            try:
                shortcut(appdata / "Start Menu/Programs/Startup/Pentarch.lnk", f'-I "{APP / "pentarch.py"}" --quiet', icon)
            except (subprocess.CalledProcessError, OSError):
                print(t("  Açılış kısayolu oluşturulamadı; Pentarch'ı elle başlatırsın, gerisi etkilenmez.",
                        "  Couldn't create the startup shortcut; start Pentarch by hand, nothing else is affected."))
        if opt(t("Masaüstüne panel kısayolu eklensin mi?", "Add a desktop shortcut for the panel?"), True):
            # the real Desktop folder: OneDrive often moves it away from %USERPROFILE%\Desktop
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                               capture_output=True, text=True)
            desk = Path(r.stdout.strip() or Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop")
            safe = re.sub(r'[<>:"/\\|?*]', "", cfg["name"]) or "Pentarch"
            try:
                shortcut(desk / f"{safe}.lnk", f'-I "{APP / "pentarch.py"}" --panel', icon)
            except (subprocess.CalledProcessError, OSError):
                print(t("  Masaüstü kısayolu oluşturulamadı; paneli `python app/pentarch.py --panel` ile aç.",
                        "  Couldn't create the desktop shortcut; open the panel with `python app/pentarch.py --panel`."))

    step("Eşleşme ve başlatma", "Pairing and start")
    started = pair_and_start(cli, cfg["name"])
    if os.name == "posix" and not TERMUX and hazir(cli):
        started = service_setup()  # the service is the background start here; it must come after pairing (one getUpdates reader)
    todo = []
    if cli == "api" and not api.get("base_url"):
        todo.append(t("beyin için bir model servisi gir: python setup.py (Ajan adımında 5)",
                      "give the brain a model service: python setup.py (Agent step, option 5)"))
    elif not hazir(cli):
        npm = "npm.cmd" if os.name == "nt" else "npm"  # PowerShell's script policy often blocks npm.ps1
        todo.append(t(f"{cli} programını kur ve giriş yap: {npm} i -g {NPM_PKG[cli]}, sonra {LOGIN[cli][0]}",
                      f"install {cli} and log in: {npm} i -g {NPM_PKG[cli]}, then {LOGIN[cli][0]}"))
    if not (SECRETS / "telegram.txt").exists() and not any((g or {}).get("enabled") for g in gateways.values()):
        todo.append(t("Telegram botunu kur: python setup.py (Telegram adımı)", "set up the Telegram bot: python setup.py (Telegram step)"))
    print(t("\nBitti.", "\nDone."))
    if not TERMUX:
        print(t("Asistan bu bilgisayarda çalışır: bilgisayar kapalıyken ya da uykudayken Telegram'dan cevap vermez.",
                "The assistant runs on this computer: while it is off or asleep, it won't answer on Telegram."))
        if os.name == "nt":
            print(t("  Gün boyu cevap versin diye: Ayarlar > Sistem > Güç > Ekran ve uyku > 'Prize takılıyken uyku: Hiçbir zaman'. Ekranın kapanması sorun değil.\n"
                    "  Dizüstüyse: Denetim Masası > Güç Seçenekleri > 'Kapağı kapattığımda' > Prize takılı: 'Hiçbir şey yapma'.",
                    "  To keep it answering all day: Settings > System > Power > Screen and sleep > 'When plugged in, put my device to sleep after: Never'. The screen going off is fine.\n"
                    "  On a laptop: Control Panel > Power Options > 'Choose what closing the lid does' > Plugged in: 'Do nothing'."))
        elif sys.platform == "darwin":
            print(t("  Gün boyu cevap versin diye: Sistem Ayarları > Pil > Seçenekler > 'Ekran kapalıyken prizdeyken otomatik uykuyu engelle' açık. "
                    "Kapak kapalıyken Mac yine uyur.",
                    "  To keep it answering all day: System Settings > Battery > Options > 'Prevent automatic sleeping on power adapter "
                    "when the display is off' on. With the lid closed the Mac still sleeps."))
    if todo:
        print(t("Asistanı başlatmadan önce:", "Before starting the assistant:") + "".join(f"\n  - {x}" for x in todo))
    if not started:
        run = f"& \"{sys.executable}\" -I \"{APP / 'pentarch.py'}\"" if os.name == "nt" else f"\"{sys.executable}\" -I \"{APP / 'pentarch.py'}\""
        print(t(f"Başlatmak için:  {run}", f"Start it with:  {run}"))
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
