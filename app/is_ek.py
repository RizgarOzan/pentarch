"""PostToolUse hook: passes an addition the owner wrote later on to a running job (PENTARCH_IS environment variable).
pentarch.py appends the addition to <home>/isler/<id>.ek; the job sees it after its next tool call. It also writes the
job's latest step to <id>.adim (panel "doing now" line) and appends it to <id>.adimlar (job history).
A subagent's tool call does not take the addition: it belongs to the main job."""
import json
import os
import sys
import time
from pathlib import Path

i = os.environ.get("PENTARCH_IS")
if not i:
    sys.exit(0)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script folder off sys.path
from config import HOME, OWNER, T  # noqa: E402

try:
    girdi = json.load(sys.stdin)
except Exception:
    girdi = {}
f = HOME / "isler" / f"{i}.ek"
try:
    g = girdi.get("tool_input") or {}
    ad = str(girdi.get("tool_name") or "")
    ne = {"Read": T("dosya okudu", "read a file"), "Edit": T("dosya düzenledi", "edited a file"),
          "Write": T("dosya yazdı", "wrote a file"), "Bash": T("komut çalıştırdı", "ran a command"),
          "PowerShell": T("komut çalıştırdı", "ran a command"), "Grep": T("dosyalarda aradı", "searched files"),
          "Glob": T("dosya aradı", "looked for files"), "Agent": T("alt oturum açtı", "opened a subagent"),
          "Task": T("alt oturum açtı", "opened a subagent"), "WebSearch": T("internette aradı", "searched the web"),
          "WebFetch": T("sayfa okudu", "read a page")}.get(ad, ad.split("__")[-1].replace("_", " "))
    ayr = str(g.get("description") or g.get("query") or g.get("pattern") or g.get("url")
              or Path(str(g.get("file_path") or "")).name or "")
    satir = ((T("alt oturum · ", "subagent · ") if girdi.get("agent_id") else "")
             + f"{ne}{': ' + ayr[:90] if ayr else ''} ({time.strftime('%H:%M')})")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.with_suffix(".adim").write_text(satir, encoding="utf-8")
    with f.with_suffix(".adimlar").open("a", encoding="utf-8") as a:
        a.write(satir + "\n")
except Exception:
    pass
if girdi.get("agent_id"):
    sys.exit(0)
alinan = f.with_suffix(".alindi")
try:
    os.replace(f, alinan)  # move first: if pentarch.py appends right now it writes a new file and no line is lost
    metin = alinan.read_text(encoding="utf-8").strip()
    alinan.unlink()
except OSError:
    sys.exit(0)
if metin:  # the key is only in the job prompt and the environment; it tells a forged tag in tool output apart
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
          f"[Pentarch-ek {os.environ.get('PENTARCH_IS_ANAHTAR', '')}] {OWNER} wrote this while you were working; "
          f"apply it now, fix what you already did if needed, and mention it in your last reply:\n{metin}"}},
          ensure_ascii=False))
