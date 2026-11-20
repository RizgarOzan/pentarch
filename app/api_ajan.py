"""agent.cli = "api": the brain is an OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, OpenRouter...) with no CLI.

Pentarch runs the tool loop itself, with a small fixed tool set:
  read_file / list_files  inside the notes folder, the Pentarch home (never secrets/) and extra_dirs
  write_file              .md/.txt in the notes folder, never in a dot folder; not on scheduled runs (oto) or runs
                          carrying outside text
  pentarch                Pentarch's own commands (reminders, tasks, routines, search, shifts); agent runs turn
                          routine/responsibility adds into a Yes/No for the owner, as with every CLI
Runs carrying outside text (salt_okur) get no tools at all. No shell, no web: those need a real agent CLI.
The day's chat is one session: its messages are kept in HOME/tmp/api-<id>.json and sent again next turn.
"""
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import agents
from config import EXTRA_DIRS, HOME, NOTES, SECRETS, T, agent_env

APP = Path(__file__).resolve().parent
ADIM = 12              # tool rounds per message
GECMIS = 60            # messages kept in a session
OKU_SINIR = 30_000     # characters a read hands back
KOMUTLAR = {"hatirlat", "remind", "gorev", "task", "bekle", "wait", "ara", "search", "vardiya", "shifts", "alacak", "receivables", "ders", "study", "etkinlik", "event",
            "rutin", "routine", "sorumluluk", "responsibility"}
# A reading run writes nothing: a task it queued would later run with the full tool set and no Yes/No, so a planted
# line in a mail it read could become one. It asks with an ÖNERİ:/PROPOSAL: line in its answer instead.
OTO_KOMUTLAR = {"ara", "search", "vardiya", "shifts", "alacak", "receivables", "ders", "study"}
YAZI_UZANTI = {".md", ".txt"}
TUR_SINIR = 8          # tool calls run per round; the rest are dropped


def _arac(ad, aciklama, **ozellik):
    return {"type": "function", "function": {"name": ad, "description": aciklama, "parameters": {
        "type": "object", "properties": ozellik, "required": list(ozellik)}}}


def araclar(oto):
    yol = {"type": "string", "description": "file or folder path; relative paths are inside the notes folder"}
    liste = [_arac("read_file", "Read a text file.", path=yol),
             _arac("list_files", "List a folder.", path=yol),
             _arac("pentarch", "Run a Pentarch command: remind \"YYYY-MM-DD HH:MM\" \"text\" | task \"title\" \"job\" | "
                   "wait \"where\" \"what\" | search words | shifts [date] | routine list | routine add NAME TIME JOB.",
                   args={"type": "array", "items": {"type": "string"}})]
    if not oto:
        liste.insert(2, _arac("write_file", "Create or overwrite a .md or .txt file in the notes folder.", path=yol,
                              content={"type": "string"}))
    return liste


def _yol(p, yazma=False):
    """The resolved path when it is allowed, else None."""
    try:
        y = (NOTES / p).resolve() if not Path(p).expanduser().is_absolute() else Path(p).expanduser().resolve()
    except (OSError, ValueError):
        return None
    kokler = [NOTES] if yazma else [NOTES, HOME, *EXTRA_DIRS]
    if y == SECRETS.resolve() or SECRETS.resolve() in y.parents:
        return None
    if yazma:  # notes only, plain text only: no .git/config, .claude/settings.json, plugin code or n.md:stream
        try:
            parca = y.relative_to(NOTES.resolve()).parts
        except ValueError:
            return None
        if not parca or y.suffix.lower() not in YAZI_UZANTI or any(p.startswith(".") or ":" in p for p in parca):
            return None
    return y if any(y == k.resolve() or k.resolve() in y.parents for k in kokler) else None


def calistir_arac(ad, girdi, kind, oto):
    try:
        if ad in ("read_file", "list_files", "write_file"):
            y = _yol(str(girdi.get("path") or ""), yazma=ad == "write_file")
            if y is None:
                return T("izin yok: bu klasörün dışı", "not allowed: outside the allowed folders")
            if ad == "read_file":
                if not y.is_file():  # a folder, a FIFO, a device
                    return T("okunamaz: dosya değil", "can't read: not a file")
                with open(y, encoding="utf-8", errors="replace") as f:
                    return f.read(OKU_SINIR)
            if ad == "list_files":
                return "\n".join(sorted(f.name + ("/" if f.is_dir() else "") for f in y.iterdir())[:300])
            if oto:
                return T("izin yok: bu koşu yalnız okur", "not allowed: this run only reads")
            y.parent.mkdir(parents=True, exist_ok=True)
            y.write_text(str(girdi.get("content") or ""), encoding="utf-8")
            return T("yazıldı", "written")
        if ad == "pentarch":
            args = [str(a) for a in girdi.get("args") or []]
            if not args or args[0] not in (OTO_KOMUTLAR if oto else KOMUTLAR):
                return T("bu komut burada yok", "that command is not available here")
            if oto and args[0] in ("alacak", "receivables") and args[1:2] and args[1] != "":
                return T("izin yok: bu koşu yalnız okur", "not allowed: this run only reads")
            r = subprocess.run([sys.executable, "-I", str(APP / "pentarch.py"), *args], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120, env=agent_env(PENTARCH_KIND=kind or "telegram"),
                               creationflags=agents.NO_WINDOW)
            return (r.stdout + r.stderr)[-4000:] or "ok"
    except Exception as e:  # the model sees the error and can try another way
        return f"error: {e}"[:500]
    return T("bilinmeyen araç", "unknown tool")


def _oturum(sid):
    return HOME / "tmp" / f"api-{sid}.json"


def _kirp(mesajlar):
    """The last GECMIS messages, starting at a user message so no tool answer loses its call."""
    m = mesajlar[-GECMIS:]
    while m and m[0].get("role") != "user":
        m = m[1:]
    if not m:  # one message's tool chain is longer than the window: keep it whole rather than lose the day
        m = mesajlar[max((i for i, x in enumerate(mesajlar) if x.get("role") == "user"), default=len(mesajlar)):]
    return m


def calistir(prompt, timeout=600, resume=None, keep=False, salt_okur=False, oto=False, kind=None):
    """Same dict shape as agents.run_other."""
    sid = resume if resume and _oturum(resume).exists() else (str(uuid.uuid4()) if keep else None)
    gecmis = []
    if resume and _oturum(resume).exists():
        try:
            gecmis = json.loads(_oturum(resume).read_text(encoding="utf-8"))
        except ValueError:
            gecmis = []
    mesajlar = [*gecmis, {"role": "user", "content": prompt}]
    son = time.monotonic() + timeout
    hatalar = []
    for api in agents.providers():
        yeni, arac_listesi = [], None if salt_okur else araclar(oto)
        try:
            for _ in range(ADIM):
                kalan = son - time.monotonic()
                if kalan <= 5:
                    raise TimeoutError(f"no answer in {timeout} s")
                try:
                    msg, _u = agents.istek(api, mesajlar + yeni, timeout=min(kalan, 300), kisisel=True, ham=True,
                                           ek={"tools": arac_listesi} if arac_listesi else None)
                except RuntimeError as e:  # endpoint or model without tool calls: chat only. Not on 401/413/429.
                    if arac_listesi and re.search(r" HTTP (400|404|422)\b", str(e)) and "tool" in str(e).lower():
                        arac_listesi = None
                        continue
                    raise
                cagri = (msg.get("tool_calls") or [])[:TUR_SINIR]
                yeni.append({"role": "assistant", "content": msg.get("content") or "",
                             **({"tool_calls": cagri} if cagri else {})})
                if not cagri:
                    break
                for c in cagri:
                    f = c.get("function") or {}
                    try:
                        girdi = json.loads(f.get("arguments") or "{}")
                    except ValueError:
                        girdi = {}
                    yeni.append({"role": "tool", "tool_call_id": c.get("id", ""),
                                 "content": calistir_arac(f.get("name"), girdi if isinstance(girdi, dict) else {}, kind, oto)})
            cevap = next((m["content"] for m in reversed(yeni) if m["role"] == "assistant" and m["content"]), "")
        except Exception as e:  # next provider, unless a tool already ran: the next one would run it again
            hatalar.append(f"{api.get('base_url')}: {str(e)[:200]}")
            if any(m["role"] == "tool" for m in yeni):
                break
            continue
        if keep and sid:
            f = _oturum(sid)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(_kirp(mesajlar + yeni), ensure_ascii=False), encoding="utf-8")
        return {"result": cevap or T("(hata: model boş cevap verdi)", "(error: the model gave an empty answer)"),
                "is_error": not cevap, "total_cost_usd": 0, "session_id": sid if keep else None, "usage": {}, "error": ""}
    if not hatalar:
        hatalar = [T("config'te providers yok", "no providers in config")]
    elif all("personal data" in h for h in hatalar):
        hatalar.append(T("Sohbet kişisel bilgi taşır: kendi makinendeki ya da güvendiğin servise config'te \"trusted\": true ekle.",
                         "The chat carries personal data: add \"trusted\": true in config to a provider you run or trust."))
    return {"result": T("(hata: hiçbir API cevap vermedi) ", "(error: no API answered) ") + " | ".join(hatalar),
            "is_error": True, "total_cost_usd": 0, "session_id": None, "usage": {}, "error": " | ".join(hatalar)[-500:]}
