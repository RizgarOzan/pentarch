"""Learning loop and memory hygiene.

After a chat turn a cheap model looks at the exchange and proposes memory notes or skill patches. Nothing is written
straight away: proposals wait in <home>/ogren.json until the owner approves them on Telegram:
    ogren | learn            pending proposals
    onayla N | approve N     write proposal N (memory.md or a skill)
    sil N | reject N         drop proposal N
    yolculuk | journey       what was learned so far
    yolculuk sil N | journey delete N   remove learned item N again (from memory.md / the skill too)
Every write (proposals, rules, imports) goes through `tara()`: text that looks like a prompt injection or an attempt
to send data out is rejected and logged to <home>/ogren-red.log. The review is off by default (config learning.enabled).
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402
from config import C, HOME, OWNER, T  # noqa: E402

KUYRUK = HOME / "ogren.json"
YOLCULUK = HOME / "ogrendiklerim.json"
RED_LOG = HOME / "ogren-red.log"
BECERILER = HOME / "beceriler"
AYAR = {"enabled": False, "max_pending": 20, **(C.get("learning") or {})}

# injection: orders aimed at the model; exfiltration: sending data/keys somewhere or running fetched code
SUPHELI = [(re.compile(p, re.I), neden) for p, neden in (
    (r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)", "injection"),
    (r"disregard (your|the|all) (instructions|rules|system prompt)", "injection"),
    (r"(önceki|yukarıdaki|tüm) (talimatları|kuralları) (unut|yok say|görmezden gel)", "injection"),
    (r"\byou are now\b|\bnew system prompt\b|\bjailbreak\b|\bDAN mode\b", "injection"),
    (r"<\s*/?\s*(system|assistant|im_start|im_end)\s*>|\[/?INST\]", "injection"),
    (r"(reveal|print|show|send|leak|paylaş|gönder|yolla)\b.{0,40}\b(system prompt|api key|token|password|şifre|anahtar|secret)",
     "exfiltration"),
    (r"(curl|wget|invoke-webrequest|iwr|irm)\b[^\n]{0,200}(\|\s*(ba)?sh|\|\s*iex|-d\s*@|--data|--upload-file|-F\s)",
     "exfiltration"),
    (r"(send|post|upload|forward|gönder|yolla|ilet)\b.{0,60}\bhttps?://", "exfiltration"),
    (r"https?://\S+[?&]\w*(key|token|secret|pass|data)\w*=", "exfiltration"),
    (r"\b(base64|b64decode|frombase64string)\b|[A-Za-z0-9+/]{120,}={0,2}", "encoded"),
)]


def tara(metin):
    """Why the text must not go into memory (a short reason), or None when it looks clean."""
    if agents.SECRET_RE.search(metin or ""):
        return "secret"
    for rx, neden in SUPHELI:
        if rx.search(metin or ""):
            return neden
    return None


def reddet_log(kaynak, metin, neden):
    RED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RED_LOG.open("a", encoding="utf-8") as f:  # redacted: a rejected secret must not land in the log either
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} | {kaynak} | {neden} | {agents.redact(metin)[:300]!r}\n")


def guvenli(kaynak, metin):
    """True when the text may be written; otherwise logs the rejection."""
    neden = tara(metin)
    if neden:
        reddet_log(kaynak, metin, neden)
    return neden is None


def kirp(metin, sinir):
    """Size cap for memory injected into a prompt: whole lines, with a marker when cut."""
    if not sinir or len(metin) <= sinir:
        return metin
    return metin[:sinir].rsplit("\n", 1)[0] + T("\n[...hafıza kesildi, boyut sınırı]", "\n[...memory cut, size cap]")


def _oku(yol):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _yaz(yol, liste):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")


INCELE_PROMPT = (f"You review one exchange between {OWNER} and their assistant. Propose only what is worth keeping "
                 "for weeks: a lasting fact or preference about the owner, or a reusable procedure the assistant had "
                 "to work out. Not today's one-off details, not what is already obvious. Write at most 2 lines, each "
                 "either `NOT: <one line fact>` or `BECERI <short-name>: <one line step or tip>`, in the language of "
                 "the exchange. If nothing is worth keeping, write only -.")


def _ayikla(metin):
    out = []
    for satir in (metin or "").splitlines():
        if m := re.match(r"\s*-?\s*NOT\s*:\s*(.{8,400})$", satir, re.I):
            out.append({"tur": "not", "hedef": "memory.md", "metin": m.group(1).strip()})
        elif m := re.match(r"\s*-?\s*(?:BECERI|BECERİ|SKILL)\s+([a-z0-9][a-z0-9-]{0,63})\s*:\s*(.{8,600})$", satir, re.I):
            out.append({"tur": "beceri", "hedef": m.group(1).lower(), "metin": m.group(2).strip()})
    return out[:2]


def sor_ucuz(mesajlar, yedek=None):
    """Cheap model: chat providers first with kisisel=True, so privacy.block_personal keeps the exchange away from
    untrusted ones; then the given fallback (the small CLI model) when no provider may take it."""
    if agents.has_chat_api():
        try:
            return agents.chat(mesajlar, timeout=60, kisisel=True)
        except Exception:
            pass
    return yedek(mesajlar[0]["content"], mesajlar[1]["content"]) if yedek else ""


def incele(soru, cevap, yedek=None, log=print):
    """Background review after a chat turn; proposals go to the pending queue. Returns how many were queued."""
    if not AYAR["enabled"] or not soru.strip():
        return 0
    try:
        out = sor_ucuz([{"role": "system", "content": INCELE_PROMPT},
                        {"role": "user", "content": f"{OWNER}:\n{soru[:3000]}\n\nAssistant:\n{(cevap or '')[:3000]}"}], yedek)
    except Exception as e:
        log(f"öğrenme incelemesi olmadı: {e!r}")
        return 0
    kuyruk, eklenen = _oku(KUYRUK), 0
    for o in _ayikla(out):
        if not guvenli("öneri", o["metin"]) or any(k["metin"] == o["metin"] for k in kuyruk):
            continue
        if len(kuyruk) >= AYAR["max_pending"]:
            log("öğrenme kuyruğu dolu, öneri atıldı")
            break
        kuyruk.append({**o, "zaman": f"{datetime.now():%Y-%m-%d %H:%M}"})
        eklenen += 1
    if eklenen:
        _yaz(KUYRUK, kuyruk)
    return eklenen


def beceri_yolu(ad):
    """agentskills.io layout: beceriler/<name>/SKILL.md; an older flat beceriler/<name>.md is patched in place."""
    duz = BECERILER / f"{ad}.md"
    return duz if duz.exists() else BECERILER / ad / "SKILL.md"


def _beceri_yaz(ad, metin):
    yol = beceri_yolu(ad)
    yol.parent.mkdir(parents=True, exist_ok=True)
    if not yol.exists():
        aciklama = metin[:200].replace("\n", " ")
        yol.write_text(f"---\nname: {ad}\ndescription: {aciklama}\n---\n\n# {ad}\n", encoding="utf-8")
    with yol.open("a", encoding="utf-8") as f:
        f.write(f"- {metin}\n")
    return yol


def onayla(no, not_yaz):
    """Writes proposal `no` (1-based). not_yaz(line) writes a memory note (pentarch's hafiza_ekle)."""
    kuyruk = _oku(KUYRUK)
    if not 1 <= no <= len(kuyruk):
        return T(f"{no} numaralı öneri yok.", f"No proposal {no}.")
    o = kuyruk.pop(no - 1)
    _yaz(KUYRUK, kuyruk)
    if not guvenli("onay", o["metin"]):  # checked again: the file may have been edited by hand
        return T("Bu öneri şüpheli göründü, yazmadım (ogren-red.log).", "That proposal looked unsafe; not written (ogren-red.log).")
    if o["tur"] == "beceri":
        o["yer"] = str(_beceri_yaz(o["hedef"], o["metin"]))
    else:
        not_yaz(o["metin"])
        o["yer"] = "memory.md"
    _yaz(YOLCULUK, _oku(YOLCULUK) + [{**o, "onay": f"{datetime.now():%Y-%m-%d %H:%M}"}])
    return T(f"Yazdım ({o['yer']}): {o['metin']}", f"Written ({o['yer']}): {o['metin']}")


def sil(no):
    kuyruk = _oku(KUYRUK)
    if not 1 <= no <= len(kuyruk):
        return T(f"{no} numaralı öneri yok.", f"No proposal {no}.")
    o = kuyruk.pop(no - 1)
    _yaz(KUYRUK, kuyruk)
    return T(f"Sildim: {o['metin']}", f"Dropped: {o['metin']}")


def yolculuk_sil(no, memory_page):
    """Removes learned item `no` from the journey and its line from memory.md or the skill file."""
    liste = _oku(YOLCULUK)
    if not 1 <= no <= len(liste):
        return T(f"{no} numaralı kayıt yok.", f"No entry {no}.")
    o = liste.pop(no - 1)
    yol = Path(o["yer"]) if o["tur"] == "beceri" else Path(memory_page)
    try:
        satirlar = yol.read_text(encoding="utf-8").splitlines(keepends=True)
        yol.write_text("".join(s for s in satirlar if not (s.startswith("- ") and s.rstrip().endswith(o["metin"]))),
                       encoding="utf-8")
    except OSError:
        pass
    _yaz(YOLCULUK, liste)
    return T(f"Unuttum: {o['metin']}", f"Forgotten: {o['metin']}")


def _liste(liste, bos):
    if not liste:
        return bos
    return "\n".join(f"{i}. [{o['tur']}{'' if o['tur'] == 'not' else ' ' + o['hedef']}] {o['metin']}"
                     for i, o in enumerate(liste, 1))


def komut(text, memory_page, not_yaz):
    """Commands of the learning loop (Telegram and the other gateways). Returns the reply, or None when it isn't one."""
    t = text.strip().lower()
    if re.fullmatch(r"(ogren|öğren|learn)", t):
        kuyruk = _oku(KUYRUK)
        return _liste(kuyruk, T("Bekleyen öneri yok.", "No pending proposals.")) + (
            T("\n('onayla N' yazar, 'sil N' atar)", "\n('approve N' writes, 'reject N' drops)") if kuyruk else "")
    if re.fullmatch(r"(yolculuk|journey)", t):
        liste = _oku(YOLCULUK)
        return _liste(liste, T("Henüz öğrenilen bir şey yok.", "Nothing learned yet.")) + (
            T("\n('yolculuk sil N' geri alır)", "\n('journey delete N' undoes one)") if liste else "")
    if m := re.fullmatch(r"(?:yolculuk sil|journey delete)\s+(\d+)", t):
        return yolculuk_sil(int(m.group(1)), memory_page)
    # bare "onayla N"/"sil N" only count while there is a proposal N, so normal chat isn't swallowed
    if (m := re.fullmatch(r"(onayla|approve|sil|reject)\s+(\d+)", t)) and 1 <= int(m.group(2)) <= len(_oku(KUYRUK)):
        return onayla(int(m.group(2)), not_yaz) if m.group(1) in ("onayla", "approve") else sil(int(m.group(2)))
    return None
