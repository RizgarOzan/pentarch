"""Extra gateways besides Telegram: e-mail (IMAP in, SMTP out) and Discord (bot token, REST polling). Off by default.

Config "gateways" (see config.py). Each incoming owner message goes through the same handling as Telegram
(pentarch.py: model-free commands first, then the chat) and the reply goes back where it came from.
- email: only mail from an address in allowed_from is read (empty list = nothing is read); unread mail is marked read.
  A From header can be forged, so keep this to an account only you write to.
- discord: only messages by owner_id in channel_id. The bot needs the Message Content intent to see the text.
State (last Discord message seen) is in <home>/gecit.json.
"""
import re
import email
import email.utils
import imaplib
import json
import os
import smtplib
import sys
import time
import urllib.request
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME  # noqa: E402

DURUM = HOME / "gecit.json"
DISCORD = "https://discord.com/api/v10"


def ayar(ad):
    return (C.get("gateways") or {}).get(ad) or {}


def acik():
    return [ad for ad in ("email", "discord") if ayar(ad).get("enabled")]


def _durum():
    try:
        return json.loads(DURUM.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _durum_yaz(**alan):
    DURUM.parent.mkdir(parents=True, exist_ok=True)
    DURUM.write_text(json.dumps({**_durum(), **alan}), encoding="utf-8")


# --- e-mail ---------------------------------------------------------------

def _govde(msg):
    """Plain text body without the quoted earlier mail."""
    part = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None) if msg.is_multipart() else msg
    if part is None:
        return ""
    text = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", errors="replace")
    satirlar = []
    for s in text.splitlines():
        if s.startswith(">") or (s.startswith("On ") and s.rstrip().endswith("wrote:")) or s.rstrip().endswith("yazdı:"):
            break
        satirlar.append(s)
    return "\n".join(satirlar).strip()


def _dogrulandi(msg, kimden):
    """True when the receiving server (Authentication-Results, e.g. Gmail) saw DKIM or SPF pass for the sender's domain."""
    alan = kimden.rpartition("@")[2]
    dom = r"(?:[\w-]+\.)*" + re.escape(alan) + r"(?![\w.-])"
    for h in msg.get_all("Authentication-Results") or []:
        h = str(h).lower()
        if re.search(r"dkim=pass[^;]*header\.[id]=@?" + dom, h) or re.search(r"spf=pass[^;]*smtp\.mailfrom=(?:[^;\s@]*@)?" + dom, h):
            return True
    return False


def posta_oku(imap_sinifi=imaplib.IMAP4_SSL):
    """Unread mail from allowed senders: [(sender, subject, message_id, body)]. Everything read is marked seen."""
    a = ayar("email")
    izinli = {x.lower() for x in a.get("allowed_from") or []}
    out = []
    m = imap_sinifi(a["imap_host"])
    try:
        m.login(a["user"], os.environ.get(a.get("password_env") or "", ""))
        m.select("INBOX")
        _, ids = m.search(None, "UNSEEN")
        for i in (ids[0] or b"").split():
            _, data = m.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            kimden = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            m.store(i, "+FLAGS", "\\Seen")
            if kimden in izinli and (_dogrulandi(msg, kimden) or a.get("trust_from_header")) and (govde := _govde(msg)):
                out.append((kimden, msg.get("Subject", ""), msg.get("Message-ID", ""), govde))
    finally:
        try:
            m.logout()
        except Exception:
            pass
    return out


def posta_yaz(alici, konu, mid, metin, smtp_sinifi=smtplib.SMTP_SSL):
    a = ayar("email")
    msg = EmailMessage()
    msg["From"], msg["To"] = a["user"], alici
    msg["Subject"] = konu if konu.lower().startswith("re:") else f"Re: {konu}"
    if mid:
        msg["In-Reply-To"] = msg["References"] = mid
    msg.set_content(metin)
    with smtp_sinifi(a["smtp_host"], int(a.get("smtp_port") or 465)) as s:
        s.login(a["user"], os.environ.get(a.get("password_env") or "", ""))
        s.send_message(msg)


def posta_tur(isle, **kw):
    for kimden, konu, mid, govde in posta_oku(**kw):
        posta_yaz(kimden, konu, mid, isle(govde, "E-mail") or "-")


# --- Discord --------------------------------------------------------------

def _discord(yol, veri=None):
    tok = os.environ.get(ayar("discord").get("token_env") or "", "")
    req = urllib.request.Request(DISCORD + yol, json.dumps(veri).encode() if veri is not None else None, {
        "Authorization": f"Bot {tok}", "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://github.com/pentarch, 1.0)"})  # Discord refuses urllib's default agent
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


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
        if str(m.get("author", {}).get("id")) == str(a["owner_id"]) and m.get("content", "").strip():
            cevap = isle(m["content"], "Discord") or "-"
            for i in range(0, len(cevap), 2000):  # Discord's message limit
                _discord(f"/channels/{kanal}/messages", {"content": cevap[i:i + 2000]})


def calis(ad, isle, log=print):
    """Loop for one gateway (run in a thread); errors are logged and the loop goes on."""
    tur = {"email": posta_tur, "discord": discord_tur}[ad]
    while True:
        try:
            tur(isle)
        except Exception as e:
            log(f"{ad} geçidi hatası: {e!r}"[:300])
        time.sleep(max(5, int(ayar(ad).get("every") or 60)))
