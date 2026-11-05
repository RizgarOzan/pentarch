"""Telegram side of Pentarch: sends messages to the owner and reads their replies.

Kullanım:
    python tg.py send "mesaj"
    python tg.py send "mesaj" --buttons "Evet|Hayır|Sonra"   (the pressed button goes to the assistant)
    python tg.py photo "C:/yol/resim.png" ["alt yazı"]
    python tg.py doc "C:/yol/dosya.pdf" ["alt yazı"]   (PDF vb. belge olarak)
    python ses.py "metin"   (sesli mesaj; send_voice burada, ses üretimi ses.py'de)
    python tg.py read

Token: <home>/secrets/telegram.txt (the single line BotFather gives) or the PENTARCH_TELEGRAM_TOKEN env var.
State: <home>/secrets/telegram-state.json (owner chat_id and last read update).
The first private chat that messages the bot claims it as owner; every other chat is ignored.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import os  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from config import HOME, NAME, SECRETS, T  # noqa: E402

TOKEN_FILE = SECRETS / "telegram.txt"
STATE_FILE = SECRETS / "telegram-state.json"
LOG_FILE = HOME / "konusma.log"


def token():
    t = os.environ.get("PENTARCH_TELEGRAM_TOKEN") or (TOKEN_FILE.read_text(encoding="utf-8").strip()
                                                      if TOKEN_FILE.exists() else "")
    if not t:
        raise RuntimeError(T(f"Telegram token yok: {TOKEN_FILE} (setup.py yazar)",
                             f"No Telegram token: {TOKEN_FILE} (setup.py writes it)"))
    return t


def api(method, http_timeout=20, **params):
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token()}/{method}", data, timeout=http_timeout) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        body = json.load(e)  # 429 gibi hatalarda gövde yine JSON'dur (ok: false)
    if not body.get("ok"):
        wait = (body.get("parameters") or {}).get("retry_after")
        if wait and http_timeout != 0:  # Telegram "retry_after" dediyse bir kez bekleyip yeniden dener
            time.sleep(min(int(wait), 60))
            return api(method, http_timeout=0, **params)
        raise RuntimeError(T(f"Telegram hatası: {body.get('description')}", f"Telegram error: {body.get('description')}"))
    return body["result"]


def keyboard(buttons):
    """Mesajın altına düğmeler; callback_data düğmenin sırası (64 bayt sınırı Türkçe metne yetmeyebilir)."""
    return json.dumps({"inline_keyboard": [[{"text": b, "callback_data": str(i)} for i, b in enumerate(buttons)]]})


def download(file_id, dest):
    tok = token()
    path = api("getFile", file_id=file_id)["file_path"]
    dest = Path(dest).with_suffix(Path(path).suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{tok}/{path}", timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def log(who, text):
    """Appends one line to the conversation log; jobs and new sessions read context from it."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    import agents  # late: tg.py also runs on its own from the shell
    line = agents.redact(text).replace("\n", " / ")
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} | {who}: {line}\n")


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"chat_id": None, "offset": 0}


def read(state):
    for upd in api("getUpdates", offset=state["offset"], timeout=0):
        state["offset"] = upd["update_id"] + 1
        msg = upd.get("message")
        if not msg or msg["chat"]["type"] != "private":
            continue
        if state["chat_id"] is None:
            state["chat_id"] = msg["chat"]["id"]
            print(T("sahip kaydedildi", "owner claimed") + f": @{msg['from'].get('username')} ({msg['from'].get('first_name')})")
        if msg["chat"]["id"] != state["chat_id"]:
            continue
        when = datetime.fromtimestamp(msg["date"]).strftime("%Y-%m-%d %H:%M")
        print(f"{when} | {msg.get('text', '(metin değil)')}")


def send(state, text, buttons=None):
    if state["chat_id"] is None:
        read(state)
    if state["chat_id"] is None:
        sys.exit(T("Sahip yok: önce bota Telegram'dan /start yaz.", "No owner yet: send /start to the bot in Telegram first."))
    extra = {"reply_markup": keyboard(buttons)} if buttons else {}
    api("sendMessage", chat_id=state["chat_id"], text=text, **extra)
    print(T("gönderildi", "sent"))


def send_photo(state, path, caption=""):
    """Resmi sıkıştırmadan belge olarak değil, fotoğraf olarak yollar (multipart)."""
    if state["chat_id"] is None:
        sys.exit(T("Sahip yok: önce bota Telegram'dan /start yaz.", "No owner yet: send /start to the bot in Telegram first."))
    tok = token()
    boundary = "----pentarch"
    parts = []
    for name, value in (("chat_id", state["chat_id"]), ("caption", caption)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{Path(path).name}"\r\n'
                 'Content-Type: image/png\r\n\r\n'.encode() + Path(path).read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendPhoto", b"".join(parts),
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if not json.load(r).get("ok"):
            sys.exit("fotoğraf gönderilemedi")
    print(T("gönderildi", "sent"))


def send_doc(state, path, caption=""):
    """Dosyayı belge olarak yollar (PDF vb.)."""
    if state["chat_id"] is None:
        sys.exit(T("Sahip yok: önce bota Telegram'dan /start yaz.", "No owner yet: send /start to the bot in Telegram first."))
    tok = token()
    boundary = "----pentarch"
    parts = []
    for name, value in (("chat_id", state["chat_id"]), ("caption", caption)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{Path(path).name}"\r\n'
                 'Content-Type: application/octet-stream\r\n\r\n'.encode() + Path(path).read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendDocument", b"".join(parts),
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        if not json.load(r).get("ok"):
            sys.exit("belge gönderilemedi")
    print(T("gönderildi", "sent"))


def send_voice(state, path, caption=""):
    """ogg/opus dosyasını Telegram sesli mesajı olarak yollar."""
    if state["chat_id"] is None:
        sys.exit(T("Sahip yok: önce bota Telegram'dan /start yaz.", "No owner yet: send /start to the bot in Telegram first."))
    tok = token()
    boundary = "----pentarch"
    parts = []
    for name, value in (("chat_id", state["chat_id"]), ("caption", caption[:1000])):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; filename="{Path(path).name}"\r\n'
                 'Content-Type: audio/ogg\r\n\r\n'.encode() + Path(path).read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendVoice", b"".join(parts),
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        if not json.load(r).get("ok"):
            sys.exit("ses gönderilemedi")
    print(T("gönderildi", "sent"))


def main():
    try:
        token()
    except RuntimeError as e:
        sys.exit(str(e))
    state = load_state()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "read":
        read(state)
        save_state(state)
    elif cmd == "send" and len(sys.argv) > 2:
        args, buttons = sys.argv[2:], None
        if "--buttons" in args:
            i = args.index("--buttons")
            buttons = [b.strip() for b in args[i + 1].split("|") if b.strip()]
            args = args[:i] + args[i + 2:]
        had_chat = state["chat_id"] is not None
        send(state, " ".join(args), buttons)
        if not had_chat:
            save_state(state)
        log(NAME, " ".join(args) + (f" [{' / '.join(buttons)}]" if buttons else ""))
    elif cmd == "photo" and len(sys.argv) > 2:
        caption = " ".join(sys.argv[3:])
        send_photo(state, sys.argv[2], caption)
        log(NAME, f"[ekran görüntüsü] {caption}".strip())
    elif cmd == "doc" and len(sys.argv) > 2:
        caption = " ".join(sys.argv[3:])
        send_doc(state, sys.argv[2], caption)
        log(NAME, f"[belge {Path(sys.argv[2]).name}] {caption}".strip())
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
