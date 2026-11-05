"""Message bridge from the assistant (a claude -p run) to a Claude chat open on the desktop.

Usage:
    python -I kopru.py send "message"    the assistant writes one line
    python -I kopru.py read [N]          last N lines (default 20)

Lines are appended to <home>/kopru.jsonl. A Monitor (tail -F) open in the desktop chat watches the file, and every
new line arrives in that chat as an event. The desktop chat answers on Telegram with tg.py send; that also lands in
konusma.log.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import HOME, NAME, T  # noqa: E402

FILE = HOME / "kopru.jsonl"


def send(text, sender=NAME.lower()):
    line = {"t": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "from": sender, "text": text}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    print(T("gönderildi", "sent"))


def read(n):
    if not FILE.exists():
        return
    for raw in FILE.read_text(encoding="utf-8").splitlines()[-n:]:
        d = json.loads(raw)
        print(f"{d['t']} | {d['from']}: {d['text']}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "send" and len(sys.argv) > 2:
        send(" ".join(sys.argv[2:]))
    elif cmd == "read":
        read(int(sys.argv[2]) if len(sys.argv) > 2 else 20)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
