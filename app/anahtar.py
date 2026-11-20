"""Step-by-step key guide for setup: what a service is, whether it is needed, where to sign up and get the key,
then a format check and a free test call. Used by setup.py and koltuk.py; the caller passes its own t/yes/secret.

    key = anahtar.ask("groq", t, yes, secret)   # "" = skipped
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
import webbrowser

# name -> what it is, needed?, free tier, sign-up page, key page, steps (tr, en), key pattern, test call.
# Every text is a (tr, en) pair. Test: (url, headers) where "{key}" is filled in; it must answer 401/403 to a bad key.
# Checked against each provider's docs and with fake keys on 2026-11-17; a public /models (OpenRouter, NVIDIA) can't test a key.
GUIDES = {
    "openrouter": {
        "what": ("Tek anahtarla birçok modele ulaştıran bir aracı; ucuz işler ve konsey koltukları için.",
                 "One key that reaches many models; used for cheap jobs and council seats."),
        "need": ("İsteğe bağlı", "Optional"),
        "free": ("Adı ':free' ile biten modeller ücretsiz: dakikada 20, günde 50 istek.", "Models ending in ':free' are free: 20 requests a minute, 50 a day."),
        "signup": "https://openrouter.ai/",
        "keys": "https://openrouter.ai/keys",
        "steps": (("Sağ üstten Sign in: Google ya da GitHub ile giriş yap.", "Click Sign in at the top right and use Google or GitHub."),
                  ("Anahtar sayfasında Create key'e bas; adı önemsiz, limit boş kalabilir.", "On the keys page press Create key; any name, leave the limit empty."),
                  ("Anahtarı kopyala (sk-or-v1- ile başlar), aşağıya yapıştır.", "Copy the key (it starts with sk-or-v1-) and paste it below."),
                  ("404 alırsan Settings > Privacy'den ücretsiz model kullanımını aç.", "If free models give 404, allow them under Settings > Privacy.")),
        "pattern": r"sk-or-v1-[0-9a-f]{64}",
        "test": ("https://openrouter.ai/api/v1/key", {"Authorization": "Bearer {key}"}),
    },
    "groq": {
        "what": ("Açık modelleri çok hızlı çalıştıran bir servis; ucuz işler ve istersen sesli notlar için.",
                 "A service that runs open models very fast; for cheap jobs and, if you like, voice notes."),
        "need": ("İsteğe bağlı", "Optional"),
        "free": ("Ücretsiz planı var.", "Has a free plan."),
        "signup": "https://console.groq.com/",
        "keys": "https://console.groq.com/keys",
        "steps": (("E-posta, Google ya da GitHub ile giriş yap.", "Sign in with e-mail, Google or GitHub."),
                  ("Anahtar sayfasında Create API Key'e bas, bir ad ver.", "On the keys page press Create API Key and give it a name."),
                  ("Anahtarı hemen kopyala (bir daha gösterilmez), aşağıya yapıştır.",
                   "Copy the key right away (it is shown only once) and paste it below.")),
        "pattern": r"[A-Za-z0-9_-]{30,}",
        "test": ("https://api.groq.com/openai/v1/models", {"Authorization": "Bearer {key}"}),
    },
    "nvidia": {
        "what": ("NVIDIA'nın barındırdığı büyük açık modeller; ucuz işler ve konsey koltukları için.",
                 "Large open models hosted by NVIDIA; for cheap jobs and council seats."),
        "need": ("İsteğe bağlı", "Optional"),
        "free": ("Hesapla süreli ücretsiz deneme kredisi gelir.", "The account comes with free trial credits that expire."),
        "signup": "https://build.nvidia.com/",
        "keys": "https://build.nvidia.com/settings/api-keys",
        "steps": (("Sağ üstten Login: NVIDIA hesabı aç ya da giriş yap.", "Click Login at the top right and create or use an NVIDIA account."),
                  ("Anahtar sayfasında Generate API Key'e bas (ya da herhangi bir model sayfasında Get API Key).",
                   "On the keys page press Generate API Key (or Get API Key on any model page)."),
                  ("Anahtarı kopyala (genelde nvapi- ile başlar), aşağıya yapıştır.", "Copy the key (it usually starts with nvapi-) and paste it below.")),
        "pattern": r"[A-Za-z0-9_-]{30,}",
        "test": None,  # its /models is public and a chat call spends credit, so the key is not tested here
    },
    "anthropic": {
        "what": ("Claude'u abonelik yerine kullandıkça ödeyerek çalıştırmak için Anthropic API anahtarı.",
                 "An Anthropic API key, to run Claude pay as you go instead of on a subscription."),
        "need": ("Yalnızca plan = api ise gerekli", "Needed only when plan = api"),
        "free": ("Kullandıkça ödenir; önce kredi yüklenir.", "Pay as you go; you add credit first."),
        "signup": "https://platform.claude.com/",
        "keys": "https://platform.claude.com/settings/keys",
        "steps": (("Giriş yap, Billing'den kredi ekle.", "Sign in and add credit under Billing."),
                  ("Anahtar sayfasında Create Key'e bas, bir ad ver.", "On the keys page press Create Key and give it a name."),
                  ("Anahtarı hemen kopyala (sk-ant- ile başlar, bir daha gösterilmez), aşağıya yapıştır.",
                   "Copy the key right away (it starts with sk-ant- and is shown once) and paste it below.")),
        "pattern": r"sk-ant-[A-Za-z0-9_-]{20,}",
        "test": ("https://api.anthropic.com/v1/models", {"x-api-key": "{key}", "anthropic-version": "2023-06-01"}),
    },
    "telegram": {
        "what": ("Asistanla telefondan konuştuğun Telegram botunun anahtarı (token).", "The token of the Telegram bot you talk to the assistant through."),
        "need": ("Gerekli (Telegram'dan konuşmak için)", "Needed (to chat over Telegram)"),
        "free": ("Ücretsiz.", "Free."),
        "signup": "https://telegram.org/apps",
        "keys": "https://t.me/BotFather",
        "steps": (("Bu bilgisayarda https://web.telegram.org adresini aç ve telefonundaki Telegram ile giriş yap; token'ı telefondan bilgisayara taşımakla uğraşmazsın.",
                   "On this computer open https://web.telegram.org and sign in with Telegram on your phone, so the token doesn't have to travel from phone to laptop."),
                  ("BotFather bağlantısını aç (resmî bot, mavi tikli), Start'a bas.", "Open the BotFather link (the official bot, blue tick) and press Start."),
                  ("/newbot gönder; önce bir görünen ad, sonra 'bot' ile biten bir kullanıcı adı yaz.",
                   "Send /newbot, then a display name, then a username that ends in 'bot'."),
                  ("Verdiği token'ı kopyala (123456789:AA... gibi), aşağıya yapıştır.", "Copy the token it gives you (like 123456789:AA...) and paste it below.")),
        "pattern": r"\d+:[A-Za-z0-9_-]{30,}",
        "test": ("https://api.telegram.org/bot{key}/getMe", {}),
    },
    "ollama": {
        "what": ("Modelleri kendi bilgisayarında çalıştıran program; anahtar gerekmez.", "Runs models on your own computer; no key needed."),
        "need": ("İsteğe bağlı", "Optional"),
        "free": ("Ücretsiz, bilgisayarında çalışır.", "Free; runs on your computer."),
        "signup": "https://ollama.com/download",
        "keys": "",
        "steps": (("İndirip kur, sonra terminalde: ollama pull gemma3", "Download and install it, then in a terminal: ollama pull gemma3"),
                  ("Çalışırken http://localhost:11434 cevap verir.", "While it runs, http://localhost:11434 answers.")),
    },
    "lmstudio": {
        "what": ("Modelleri kendi bilgisayarında çalıştıran masaüstü uygulaması; anahtar gerekmez.", "A desktop app that runs models on your computer; no key needed."),
        "need": ("İsteğe bağlı", "Optional"),
        "free": ("Ücretsiz, bilgisayarında çalışır.", "Free; runs on your computer."),
        "signup": "https://lmstudio.ai/",
        "keys": "",
        "steps": (("İndirip kur, bir model indir.", "Download and install it, then download a model."),
                  ("Developer sekmesinde Start Server'a bas; sunucu http://localhost:1234 üstünde.",
                   "In the Developer tab press Start Server; it listens on http://localhost:1234.")),
    },
}


def ekran():
    """False on a Linux box with no desktop (SSH, server): a browser would open as text inside the terminal."""
    return not sys.platform.startswith("linux") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def show(name, t, yes):
    """Prints what the service is and the numbered steps, then offers to open the page in the browser."""
    g = GUIDES.get(name)
    if not g:
        return
    print(f"\n{name}: {t(*g['what'])}")
    print(f"  {t(*g['need'])}. {t(*g['free'])}")
    print(t(f"  Kayıt: {g['signup']}", f"  Sign up: {g['signup']}"))
    if g["keys"]:
        print(t(f"  Anahtar sayfası: {g['keys']}", f"  Key page: {g['keys']}"))
    for i, step in enumerate(g["steps"], 1):
        print(f"    {i}. {t(*step)}")
    page = g["keys"] or g["signup"]
    if ekran() and yes(t("  Sayfa tarayıcıda açılsın mı?", "  Open the page in your browser?"), True):
        try:
            if not webbrowser.open(page):
                raise OSError
        except Exception:
            print(t(f"  Tarayıcı açılamadı; adresi elle aç: {page}", f"  Couldn't open a browser; open it by hand: {page}"))


def looks_right(name, key):
    p = GUIDES.get(name, {}).get("pattern")
    return not p or bool(re.fullmatch(p, key))


def check(name, key, timeout=10):
    """True = the service accepted the key, False = it refused it, None = no free test or no answer (offline)."""
    test = GUIDES.get(name, {}).get("test")
    if not test:
        return None
    url, headers = test
    req = urllib.request.Request(url.replace("{key}", key), headers={k: v.replace("{key}", key) for k, v in headers.items()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            json.load(r)
        return True
    except urllib.error.HTTPError as e:
        return False if e.code in (401, 403, 404) else None
    except Exception:
        return None


def ask(name, t, yes, secret, label=""):
    """Guide, then ask for the key until it looks right and the service takes it. Empty input skips; returns the key or ""."""
    show(name, t, yes)
    g = GUIDES.get(name, {})
    if not g.get("keys"):
        return ""
    while True:
        what = label or t(f"{name} anahtarı", f"{name} key")
        key = secret(t(f"  {what} (gizli; boş = atla): ", f"  {what} (hidden; empty = skip): ")).strip()
        if not key:
            print(t("  Atlandı; kurulumu sonra yeniden çalıştırıp ekleyebilirsin.", "  Skipped; run setup again later to add it."))
            return ""
        if not looks_right(name, key):
            print(t("  ! Bu, beklenen biçimde değil. Anahtarın tamamını kopyaladığından, başında ya da sonunda boşluk kalmadığından emin ol.",
                    "  ! That doesn't look like the right format. Make sure you copied the whole key with no spaces around it."))
            if yes(t("  Yeniden yapıştırılsın mı?", "  Paste it again?"), True):
                continue
        ok = check(name, key)
        if ok is True:
            print(t("  Anahtar çalışıyor.", "  The key works."))
        elif ok is False:
            print(t(f"  ! Servis bu anahtarı kabul etmedi. Silinmiş ya da yanlış kopyalanmış olabilir; {g['keys']} sayfasında yenisini oluştur.",
                    f"  ! The service refused this key. It may be deleted or copied wrong; make a new one at {g['keys']}."))
            if yes(t("  Yeniden denensin mi?", "  Try again?"), True):
                continue
            return ""
        else:
            print(t("  Anahtar denenemedi (internet yok ya da test yok); yine de kaydediliyor.",
                    "  Couldn't test the key (offline or no free test); saving it anyway."))
        return key
