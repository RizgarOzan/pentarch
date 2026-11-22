"""Extra gateways besides Telegram: e-mail (IMAP in, SMTP out), Discord and Slack (bot token, REST polling) and Signal
(signal-cli). Off by default.

Config "gateways" (see config.py). Each incoming owner message goes through the same handling as Telegram
(pentarch.py: model-free commands first, then the chat) and the reply goes back where it came from.
- email: only mail from an address in allowed_from is read and marked read (empty list = nothing is read); other mail
  stays unread. A From header can be forged, so a message also needs a DMARC or DKIM pass for exactly the sender's
  domain in the topmost Authentication-Results header, written by our own server: known for Gmail and Yandex, for any
  other provider set auth_server (the name that header starts with), or no mail is read.
- discord: only messages by owner_id in channel_id. The bot needs the Message Content intent to see the text.
- slack: only messages by owner_id (U...) in channel_id (C... or a D... DM); bot messages and joins are skipped.
  Files are saved to <home>/gelen (files:read scope); thread replies only with "Also send to channel".
- signal: only messages from the owner number; signal-cli must already be registered or linked for account.
  Attachments are copied to <home>/gelen.
WhatsApp is not here: its official API delivers messages only to a public HTTPS webhook.
State (last Discord / Slack message seen, replies that failed to send) is in <home>/gecit.json.
"""
import re
import email
import email.header
import email.utils
import html
import imaplib
import json
import os
import shutil
import smtplib
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME, T  # noqa: E402

DURUM = HOME / "gecit.json"
DISCORD = "https://discord.com/api/v10"
SLACK = "https://slack.com/api/"


def ayar(ad):
    return (C.get("gateways") or {}).get(ad) or {}


def acik():
    return [ad for ad in ("email", "discord", "slack", "signal") if ayar(ad).get("enabled")]


def ev():
    """(door, address) where notifications go when there is no Telegram: the first open door that knows the owner."""
    for ad in acik():
        a = ayar(ad)
        if ad == "email" and (a.get("allowed_from") or a.get("user")):
            return ad, {"alici": (a.get("allowed_from") or [a["user"]])[0], "konu": C.get("name", "Pentarch"), "mid": ""}
        if ad in ("discord", "slack") and a.get("channel_id"):
            return ad, {"kanal": a["channel_id"]}
        if ad == "signal" and a.get("owner"):
            return ad, {"kendine": a["owner"] == a.get("account"), "alici": a["owner"]}
    return None


def _durum():
    try:
        return json.loads(DURUM.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_KILIT = threading.Lock()  # each gateway is its own thread, and they share gecit.json


def _durum_yaz(**alan):
    with _KILIT:
        DURUM.parent.mkdir(parents=True, exist_ok=True)
        gecici = DURUM.with_suffix(".tmp")
        gecici.write_text(json.dumps({**_durum(), **alan}), encoding="utf-8")
        os.replace(gecici, DURUM)


# --- delivery -------------------------------------------------------------

BOY = {"discord": 2000, "slack": 3500}  # message length limits


class Gonderilemedi(Exception):
    def __init__(self, kalan, neden):
        super().__init__(f"{neden!r}")
        self.kalan = kalan


def _parca(ad, metin, h):
    if ad == "discord":
        _discord(f"/channels/{h['kanal']}/messages", {"content": metin})
    elif ad == "slack":
        _slack("chat.postMessage", channel=h["kanal"], text=metin, **({"thread_ts": h["konu"]} if h.get("konu") else {}))
    elif ad == "signal" and h.get("kendine"):
        _signal("send", "--note-to-self", "--message-from-stdin", girdi=metin)
    elif ad == "signal":
        _signal("send", "--message-from-stdin", h["alici"], girdi=metin)
    else:
        posta_yaz(h["alici"], h["konu"], h["mid"], metin)


def _gonder(ad, metin, h):
    boy = BOY.get(ad) or max(len(metin), 1)
    for i in range(0, len(metin), boy):
        try:
            _parca(ad, metin[i:i + boy], h)
        except Exception as e:
            raise Gonderilemedi(metin[i:], e) from e


def teslim(ad, metin, **hedef):
    """Sends a reply. Whatever doesn't go out is kept in gecit.json and sent first next round, so a network blip
    loses no answer and the agent isn't run twice for one message."""
    try:
        _gonder(ad, metin, hedef)
    except Gonderilemedi as g:
        bek = _durum().get(f"{ad}_bekleyen", [])
        _durum_yaz(**{f"{ad}_bekleyen": (bek + [{"metin": g.kalan, "hedef": hedef}])[-20:]})


_su_an = threading.local()


def adres():
    """(door, address) of the message this thread is handling, so a long job started from it can report back there."""
    return getattr(_su_an, "v", None)


def bagla(v):
    """A job thread started from a door takes its address, so its proposals go back there too."""
    _su_an.v = v


def _cevapla(isle, metin, kaynak, ad, **hedef):
    _su_an.v = (ad, hedef)
    try:
        cevap = isle(metin, kaynak)
    finally:
        _su_an.v = None
    teslim(ad, cevap or "-", **hedef)


VAZGEC = 30  # rounds a leftover reply is retried (about an hour at the usual 2 min) before it is dropped


def _bekleyenler(ad):
    """Leftover replies go out before anything new is read. If one still fails, the round stops there, so new
    messages wait on the server (Discord, Slack) or in signal-cli / the inbox instead of piling up unanswered."""
    anahtar = f"{ad}_bekleyen"
    while bek := _durum().get(anahtar):
        try:
            _gonder(ad, bek[0]["metin"], bek[0]["hedef"])
        except Gonderilemedi as g:
            deneme = bek[0].get("deneme", 0) + 1
            if deneme < VAZGEC:
                _durum_yaz(**{anahtar: [{**bek[0], "metin": g.kalan, "deneme": deneme}, *bek[1:]]})
                raise
            # an address that rejects us or an archived channel would otherwise block this door for good
            print(f"[gecit] {ad}: reply dropped after {deneme} tries: {g.__cause__!r}", file=sys.stderr, flush=True)
        _durum_yaz(**{anahtar: bek[1:]})


# --- e-mail ---------------------------------------------------------------

def _html_metin(h):
    """text/html -> plain lines; quoted earlier mail (blockquote, Gmail's quote div) is dropped."""
    h = re.sub(r"(?is)<(script|style|blockquote)\b.*?</\1>|<div[^>]*gmail_quote.*", "", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", h)
    return html.unescape(re.sub(r"<[^>]+>", "", h))


def _govde(msg):
    """Plain text body without the quoted earlier mail; an HTML-only mail falls back to its stripped HTML."""
    parcalar = list(msg.walk())
    part = next((p for p in parcalar if p.get_content_type() == "text/plain"), None) \
        or next((p for p in parcalar if p.get_content_type() == "text/html"), None)
    if part is None:
        return ""
    text = (part.get_payload(decode=True) or b"")[:262144].decode(part.get_content_charset() or "utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        text = _html_metin(text)
    satirlar = []
    for s in text.splitlines():
        if s.startswith(">") or (s.startswith("On ") and s.rstrip().endswith("wrote:")) or s.rstrip().endswith("yazdı:"):
            break
        satirlar.append(s)
    return "\n".join(satirlar).strip()


# who writes the Authentication-Results header at the big providers; a suffix match covers Yandex's many front hosts
DOGRULAYAN = {"imap.gmail.com": "mx.google.com", "imap.yandex.com": "yandex.net", "imap.yandex.ru": "yandex.net",
              "imap.yandex.com.tr": "yandex.net"}


def _dogrulandi(msg, kimden, sunucu=""):
    """True when our own receiving server (named by `sunucu`, e.g. mx.google.com) saw DMARC or DKIM pass for exactly the
    sender's domain. Only the topmost Authentication-Results header counts: anything below came with the mail and can be
    written by the sender. With no known server nothing passes, since then the top header may be the sender's too.
    SPF alone isn't enough: a shared sending service in the owner's SPF record would let its other customers through."""
    h = str((msg.get_all("Authentication-Results") or [""])[0]).lower()
    yazan = (h.split(";", 1)[0].strip().split() or [""])[0]
    s = sunucu.lower()
    if not s or not (yazan == s or yazan.endswith("." + s)):
        return False
    dom = re.escape(kimden.rpartition("@")[2]) + r"(?![\w.-])"
    return bool(re.search(r"dmarc=pass[^;]*header\.from=" + dom, h) or re.search(r"dkim=pass[^;]*header\.(?:d=|i=@)" + dom, h))


def imap_tls(host, **kw):
    """IMAP4_SSL without a context skips certificate checks (the stdlib default is unverified); this one verifies."""
    return imaplib.IMAP4_SSL(host, ssl_context=ssl.create_default_context(), **kw)


def smtp_tls(host, port):
    return smtplib.SMTP_SSL(host, port, context=ssl.create_default_context())


def posta_oku(imap_sinifi=imap_tls):
    """Unread mail from allowed senders: [(sender, subject, message_id, body)]. Only their mail is marked seen; the rest
    of the inbox is peeked at (sender only) and stays unread."""
    a = ayar("email")
    izinli = {x.lower() for x in a.get("allowed_from") or []}
    out = []
    m = imap_sinifi(a["imap_host"])
    try:
        m.login(a["user"], os.environ.get(a.get("password_env") or "", ""))
        m.select("INBOX")
        _, ids = m.search(None, "UNSEEN")
        for i in (ids[0] or b"").split():
            _, data = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM)])")
            kimden = email.utils.parseaddr(email.message_from_bytes(data[0][1]).get("From", ""))[1].lower()
            if kimden not in izinli:
                continue
            _, data = m.fetch(i, "(BODY.PEEK[])")
            msg = email.message_from_bytes(data[0][1])
            sunucu = a.get("auth_server") or DOGRULAYAN.get(str(a.get("imap_host") or "").lower(), "")
            if not _dogrulandi(msg, kimden, sunucu):  # a forged From stays unread in the inbox, where the owner can see it
                continue
            if govde := _govde(msg):  # a body we can't read stays unread, so the owner still sees it
                m.store(i, "+FLAGS", "\\Seen")
                out.append((kimden, msg.get("Subject", ""), msg.get("Message-ID", ""), govde))
    finally:
        try:
            m.logout()
        except Exception:
            pass
    return out


def posta_yaz(alici, konu, mid, metin, smtp_sinifi=smtp_tls, yanit=True):
    a = ayar("email")
    msg = EmailMessage()
    msg["From"], msg["To"] = a["user"], alici
    msg["Subject"] = konu if not yanit or konu.lower().startswith("re:") else f"Re: {konu}"
    if mid:
        msg["In-Reply-To"] = msg["References"] = mid
    msg.set_content(metin)
    with smtp_sinifi(a["smtp_host"], int(a.get("smtp_port") or 465)) as s:
        s.login(a["user"], os.environ.get(a.get("password_env") or "", ""))
        s.send_message(msg)


AYLAR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")  # IMAP dates, not the locale's


def posta_hazir():
    """True when an IMAP account is set, even with the e-mail door off: the mail check routine can then read the inbox."""
    a = ayar("email")
    return bool(a.get("imap_host") and a.get("user") and os.environ.get(a.get("password_env") or ""))


def _ozet(msg, n=300):
    """The first n characters of the readable body: plain text, else HTML with the tags dropped."""
    return " ".join(_govde(msg).split())[:n]


def posta_basliklar(since, imap_sinifi=imap_tls, en_cok=40, ozet=False):
    """'sender | subject' for inbox mail dated after since ("YYYY-MM-DD HH:MM", local time), oldest first. The inbox is
    opened read-only and everything is fetched with PEEK: nothing is marked seen. ozet=True adds ' | ' and the first
    300 characters of the body (only the first 64 KB of each mail is fetched); the caller must hand that to a run
    with no tools."""
    a = ayar("email")
    sinir = datetime.strptime(since, "%Y-%m-%d %H:%M").astimezone()
    out = []
    m = imap_sinifi(a["imap_host"], timeout=60)  # a hung server must not hold the routine forever
    try:
        m.login(a["user"], os.environ.get(a.get("password_env") or "", ""))
        m.select("INBOX", readonly=True)
        _, ids = m.search(None, "SINCE", f"{sinir.day}-{AYLAR[sinir.month - 1]}-{sinir.year}")
        for i in (ids[0] or b"").split()[-en_cok:]:
            _, data = m.fetch(i, "(BODY.PEEK[]<0.65536>)" if ozet else "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            try:  # one malformed mail (bad header encoding, odd charset) is skipped, not the whole check
                msg = email.message_from_bytes(data[0][1])
                try:
                    tarih = email.utils.parsedate_to_datetime(msg.get("Date", ""))
                except (TypeError, ValueError):
                    tarih = None
                if tarih and tarih.tzinfo and tarih < sinir:
                    continue
                konu = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))
                ad, adres = email.utils.parseaddr(str(email.header.make_header(email.header.decode_header(msg.get("From", "")))))
            except Exception:
                continue
            # The display name and subject are the sender's words: one line each, no "|" so they can't fake a column.
            ad, konu = (" ".join(x.replace("|", "/").split()) for x in (ad, konu))
            satir = f"{ad[:80] + ' ' if ad else ''}<{adres[:120]}> | {konu[:150]}"
            if ozet:
                try:
                    satir += f" | {_ozet(msg)}"
                except Exception:  # a broken or cut-off MIME part leaves the line as sender and subject
                    pass
            out.append(satir)
    finally:
        try:
            m.logout()
        except Exception:
            pass
    return out


def posta_tur(isle, **kw):
    for kimden, konu, mid, govde in posta_oku(**kw):
        _cevapla(isle, govde, "E-mail", "email", alici=kimden, konu=konu, mid=mid)


# --- Discord --------------------------------------------------------------

def _discord(yol, veri=None, retry=False):
    tok = os.environ.get(ayar("discord").get("token_env") or "", "")
    req = urllib.request.Request(DISCORD + yol, json.dumps(veri).encode() if veri is not None else None, {
        "Authorization": f"Bot {tok}", "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://github.com/pentarch, 1.0)"})  # Discord refuses urllib's default agent
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        if e.code != 429 or retry:
            raise
        wait = min(float(e.headers.get("Retry-After") or 1), 30)  # Discord says how long; one polite retry, then fail
        time.sleep(wait)
        return _discord(yol, veri, retry=True)


def discord_tur(isle):
    """New owner messages in the channel are handled in order and answered there. The first run only marks the spot."""
    a = ayar("discord")
    kanal, son = a["channel_id"], _durum().get("discord_son")
    if not son:
        mesajlar = _discord(f"/channels/{kanal}/messages?limit=1")
        _durum_yaz(discord_son=mesajlar[0]["id"] if mesajlar else "0")
        return
    for m in sorted(_discord(f"/channels/{kanal}/messages?after={son}&limit=50"), key=lambda m: int(m["id"])):
        _durum_yaz(discord_son=m["id"])
        if str(m.get("author", {}).get("id")) == str(a["owner_id"]):
            metin = " ".join(x for x in (m.get("content", "").strip(), discord_dosyalari(m)) if x)
            if metin:
                _cevapla(isle, metin, "Discord", "discord", kanal=kanal)


# --- Slack ----------------------------------------------------------------

SLACK_IPUCU = {"not_in_channel": "invite the bot to the channel (/invite @bot)",
               "channel_not_found": "check channel_id, and for a DM turn on the Messages tab under App Home",
               "invalid_auth": "check the token", "missing_scope": "add channels:history, groups:history or im:history, "
               "and chat:write, then reinstall the app", "ratelimited": "raise gateways.slack.every"}


def _slack(metod, **veri):
    tok = os.environ.get(ayar("slack").get("token_env") or "", "")
    if not tok.startswith("xoxb-"):
        # a user token (xoxp-) posts as the owner, so every reply would come back as a new owner message
        raise RuntimeError("slack: use the bot token (xoxb-), not a user token")
    if metod == "chat.postMessage":
        req = urllib.request.Request(SLACK + metod, json.dumps(veri).encode(), {
            "Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=utf-8"})
    else:
        req = urllib.request.Request(SLACK + metod + "?" + urllib.parse.urlencode(veri), headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        cevap = json.loads(r.read())
    if not cevap.get("ok"):
        hata = cevap.get("error")
        raise RuntimeError(f"slack {metod}: {hata}" + (f" ({SLACK_IPUCU[hata]})" if hata in SLACK_IPUCU else ""))
    return cevap


def slack_metni(s):
    """Slack markup to plain text: <@U1> -> @U1, <#C1|genel> -> #genel, <https://x|doc> -> doc (https://x); then the
    &amp; &lt; &gt; escapes."""
    def cevir(m):
        hedef, _, ad = m.group(1).partition("|")
        if hedef[:1] in "@#":
            return hedef[0] + (ad or hedef[1:])
        return f"{ad} ({hedef})" if ad else hedef
    return html.unescape(re.sub(r"<([^<>]+)>", cevir, s))


GELEN = HOME / "gelen"  # where Telegram files land too; the agent may read this folder
DOSYA_SINIR = 20 * 1024 * 1024


class _Yonlendirme(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # the bot token must not follow a redirect anywhere
        return None


_YONSUZ = urllib.request.build_opener(_Yonlendirme)


def _guvenli_ad(ad):
    return re.sub(r"[^\w.-]", "_", Path(str(ad or "dosya")).name)[-80:] or "dosya"


def slack_dosyalari(m):
    """Files on a Slack message are saved to gelen/ (needs the files:read scope) and described for the agent as
    "(sent a file: path)". One that can't be fetched is still named, so the owner hears why."""
    tok = os.environ.get(ayar("slack").get("token_env") or "", "")
    out = []
    for f in m.get("files") or []:
        ad = _guvenli_ad(f.get("name"))
        url = f.get("url_private_download") or f.get("url_private") or ""
        try:
            boyut = int(f.get("size") or 0)
        except (TypeError, ValueError):
            boyut = 0
        if boyut > DOSYA_SINIR or not url.startswith("https://files.slack.com/"):
            out.append(f"(sent a file that wasn't downloaded: {ad}, too big or not hosted on Slack)")
            continue
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
            with _YONSUZ.open(req, timeout=60) as r:
                veri = r.read(DOSYA_SINIR + 1)
                if "text/html" in (r.headers.get("Content-Type") or ""):  # Slack's login page: files:read is missing
                    raise RuntimeError("missing files:read scope")
            GELEN.mkdir(parents=True, exist_ok=True)
            yol = GELEN / f"slack-{_guvenli_ad(f.get('id'))}-{ad}"
            yol.write_bytes(veri[:DOSYA_SINIR])
            out.append(f"(sent a file: {yol})")
        except Exception as e:
            out.append(f"(sent a file that couldn't be downloaded: {ad}; {e}. The Slack app may need the files:read scope)")
    return " ".join(out)


def discord_dosyalari(m):
    """Attachments on a Discord message are saved to gelen/ and described as "(sent a file: path)". The CDN links are
    signed, so no token goes along; only Discord's own hosts are fetched."""
    out = []
    for f in m.get("attachments") or []:
        ad = _guvenli_ad(f.get("filename"))
        url = f.get("url") or ""
        try:
            boyut = int(f.get("size") or 0)
        except (TypeError, ValueError):
            boyut = 0
        if boyut > DOSYA_SINIR or not re.match(r"https://(cdn\.discordapp\.com|media\.discordapp\.net)/", url):
            out.append(f"(sent a file that wasn't downloaded: {ad}, too big or not hosted on Discord)")
            continue
        try:
            with _YONSUZ.open(urllib.request.Request(url), timeout=60) as r:
                veri = r.read(DOSYA_SINIR + 1)
            GELEN.mkdir(parents=True, exist_ok=True)
            if len(veri) > DOSYA_SINIR:  # the declared size lied: don't hand over a cut-off file as whole
                raise ValueError("file is bigger than the limit")
            yol = GELEN / f"discord-{_guvenli_ad(f.get('id'))}-{ad.rstrip('. ') or 'file'}"
            yol.write_bytes(veri)
            out.append(f"(sent a file: {yol})")
        except Exception as e:
            out.append(f"(sent a file that couldn't be downloaded: {ad}; {e})")
    return " ".join(out)


def slack_tur(isle):
    """Same as Discord: the owner's new messages in the channel (or DM) are handled oldest first and answered there.
    The first run only marks the spot. Files come along (slack_dosyalari). A reply inside a thread is read only when
    "Also send to channel" is ticked: fetching every thread would cost a request a minute on Slack's limit for
    non-Marketplace apps. Such a message is answered in its thread."""
    a = ayar("slack")
    kanal, son = a["channel_id"], _durum().get("slack_son")
    if not son:
        mesajlar = _slack("conversations.history", channel=kanal, limit=1)["messages"]
        _durum_yaz(slack_son=mesajlar[0]["ts"] if mesajlar else "0")
        return
    veri = _slack("conversations.history", channel=kanal, oldest=son, limit=15)
    if veri.get("has_more"):  # new non-Marketplace apps get 15 messages a minute, so older ones can't be fetched
        _slack("chat.postMessage", channel=kanal, text=T(
            "Son bakıştan beri 15'ten fazla mesaj geldi, eskileri atlandı. Botla DM'de konuşursan bu olmaz.",
            "More than 15 messages came in since my last look, so I skipped the older ones. A DM with me avoids this."))
    for m in sorted(veri["messages"], key=lambda m: float(m["ts"])):
        _durum_yaz(slack_son=m["ts"])
        if m.get("user") != a["owner_id"] or m.get("bot_id") or m.get("subtype") not in (None, "file_share", "thread_broadcast"):
            continue
        metin = " ".join(x for x in (slack_metni(m.get("text") or "").strip(), slack_dosyalari(m)) if x)
        if metin:
            _cevapla(isle, metin, "Slack", "slack", kanal=kanal, konu=m.get("thread_ts") or "")


# --- Signal (signal-cli) --------------------------------------------------

def _signal(*args, girdi=None):
    a = ayar("signal")
    cli = a.get("cli") or "signal-cli"
    yol = shutil.which(cli)  # which(): on Windows signal-cli is a .bat
    if not yol:
        raise RuntimeError(f"signal-cli not found ({cli}); install it or set gateways.signal.cli to its full path")
    r = subprocess.run([yol, "-o", "json", "-a", a["account"], *args], input=girdi,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    if r.returncode:
        raise RuntimeError(f"signal-cli: {(r.stderr or '').strip()[:200]}")
    return r.stdout


def signal_tur(isle):
    """Messages from the owner's number to the signal-cli account; everyone else's are dropped (signal-cli has already
    taken them off the server, Pentarch never reads them). Group messages are skipped. When signal-cli is linked to the
    owner's own number, "Note to Self" is the chat: those arrive as sync messages and the reply goes back there."""
    a = ayar("signal")
    sahip, hesap = _numara(a["owner"]), _numara(a["account"])
    for satir in _signal("receive", "-t", "5").splitlines():
        try:
            zarf = json.loads(satir).get("envelope") or {}
        except ValueError:
            continue
        gonderen = {_numara(zarf.get(k)) for k in ("sourceNumber", "source", "sourceUuid")}
        if not sahip or sahip not in gonderen:
            continue
        if sahip == hesap:  # own linked device: only Note to Self, never what the owner sends to other people
            m = (zarf.get("syncMessage") or {}).get("sentMessage") or {}
            if _numara(m.get("destinationNumber") or m.get("destination")) != sahip:
                continue
        else:
            m = zarf.get("dataMessage") or {}
        metin = " ".join(x for x in ((m.get("message") or "").strip(), signal_ekleri(m)) if x)
        if metin and not m.get("groupInfo") and not m.get("groupV2"):
            _cevapla(isle, metin, "Signal", "signal", kendine=sahip == hesap, alici=sahip)


def signal_ekleri(m):
    """signal-cli saves attachments itself, under <data>/signal-cli/attachments/<id> (XDG_DATA_HOME, else
    ~/.local/share, Windows included). They are copied to gelen/ so the agent finds them where Telegram files are."""
    kok = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "signal-cli" / "attachments"
    out = []
    for e in m.get("attachments") or []:
        ad = _guvenli_ad(e.get("filename") or e.get("id"))
        kaynak = kok / _guvenli_ad(e.get("id"))
        try:
            if (e.get("size") or 0) > DOSYA_SINIR:
                raise OSError("over 20 MB")
            GELEN.mkdir(parents=True, exist_ok=True)
            yol = shutil.copyfile(kaynak, GELEN / f"signal-{_guvenli_ad(e.get('id'))}-{ad}")
            out.append(f"(sent a file: {yol})")
        except OSError as h:
            out.append(f"(sent a file that couldn't be read: {ad}; {h})")
    return " ".join(out)


def _numara(s):
    """'+90 555-000 00 00' and '+905550000000' compare equal; a UUID stays as it is."""
    s = str(s or "").strip()
    return re.sub(r"[\s\-().]", "", s) if s.startswith("+") else s


def calis(ad, isle, log=print):
    """Loop for one gateway (run in a thread); errors are logged and the loop goes on."""
    tur = {"email": posta_tur, "discord": discord_tur, "slack": slack_tur, "signal": signal_tur}[ad]
    while True:
        try:
            _bekleyenler(ad)
            tur(isle)
        except Exception as e:
            log(f"{ad} geçidi hatası: {e!r}"[:300])
        time.sleep(max(5, int(ayar(ad).get("every") or 60)))
