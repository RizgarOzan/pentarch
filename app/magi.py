"""Council: several models discuss the same question at once (named after MAGI in Evangelion).
Round 1 is independent opinions, round 2 reads the others, objects and may change its mind, then a judge counts votes.
Seats come from config "council": [{"name", "kind": "agent"|"openai", "model", "base_url", "key_env", "role"?}].
"agent" runs the configured agent CLI; "openai" POSTs to {base_url}/chat/completions with the key from
os.environ[key_env]. No seats configured means one agent seat (no vote).
Usage: python -I magi.py "question"   (or the question on stdin). Do not send secrets, tokens or private messages.
Every council goes to <home>/magi/kayit.jsonl; when the owner later fills the "owner" field with their verdict,
later councils see it as an example (learning from the record, not fine-tuning)."""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME, LANG_NAME, T  # noqa: E402
import agents  # noqa: E402

KAYIT = HOME / "magi" / "kayit.jsonl"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
BAGLAM = T(f"Kısa yaz, en fazla 120 kelime, {LANG_NAME} dilinde. Rol yapma, tiyatro cümlesi kurma. İlk cümlen sorulan "
           "seçeneklerden hangisini seçtiğin olsun; 'odaklan' gibi genel öğüt cevap sayılmaz. Sonra gerekçen.",
           f"Write briefly, at most 120 words, in {LANG_NAME}. No role-play or theatrics. Your first sentence names the option "
           "you pick from the ones asked; generic advice like 'focus' is not an answer. Then your reasoning.")
ROLES = [
    ("Bilim insanısın: kanıta, mantığa, ölçülebilir sonuca bakarsın. Tahmini olgudan ayır.",
     "You are the scientist: evidence, logic, measurable results. Separate guesses from facts."),
    ("Koruyucusun: risk, maliyet, zaman, sağlık ve itibar. Neyin ters gidebileceğini söyle.",
     "You are the guardian: risk, cost, time, health and reputation. Say what can go wrong."),
    ("Hırslı ve sezgiselsin: en cesur, en ilginç seçeneği ara. Sıkıcı güvenli yolu eleştir.",
     "You are ambitious and intuitive: look for the boldest, most interesting option. Criticise the dull safe path."),
    ("Uygulayıcısın: kaç saat sürer, neyle yapılır, nerede takılır. Planı somut adıma çevir.",
     "You are the builder: how many hours, with what, where it gets stuck. Turn the plan into concrete steps."),
    ("Şüphecisin: bu işin neden boşa gideceğini, kimin zaten yaptığını, gözden kaçanı ara.",
     "You are the sceptic: why this will be wasted effort, who already does it, what is being missed."),
]
SEATS = C.get("council") or [{"name": C["agent"]["cli"].upper(), "kind": "agent", "model": C["agent"]["deep_model"]}]
UYELER = {s.get("name") or f"SEAT{i + 1}": dict(s, role=s.get("role") or T(*ROLES[i % len(ROLES)]))
          for i, s in enumerate(SEATS)}


def sor(uye, metin):
    seat = UYELER[uye]
    sistem = T(f"Sen konseyde {uye}'sın. ", f"You are {uye} on the council. ") + f"{seat['role']} {BAGLAM}"
    if seat.get("kind") == "openai":
        return api_sor(seat, sistem, metin)
    return agent_sor(seat.get("model") or C["agent"]["deep_model"], sistem, metin)


def agent_sor(model, sistem, metin, timeout=300):
    """One answer from the configured agent CLI with no tools."""
    if agents.CLI == "claude":
        p = subprocess.run([agents.exe(), "-p", "--model", model, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
                            "--disable-slash-commands", "--no-session-persistence", "--system-prompt", sistem],
                           input=metin, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=NO_WINDOW)
        if p.returncode:
            raise RuntimeError(p.stderr[-300:])
        return p.stdout.strip()
    # question first: with the system text in front, gemini tended to skip the question and give generic advice
    r = agents.run_other(f"{metin}\n\n---\n{sistem}", model=model, timeout=timeout)
    if r["is_error"] or not r["result"]:
        raise RuntimeError(r["result"][-300:])
    return r["result"]


def api_sor(seat, sistem, metin, max_tokens=4000):
    """OpenAI-compatible endpoint. The key is read from the environment and never written anywhere."""
    key = os.environ.get(seat.get("key_env") or "", "")
    istek = urllib.request.Request(seat["base_url"].rstrip("/") + "/chat/completions", headers={
        "Content-Type": "application/json", "User-Agent": "pentarch-council/1.0",  # Groq 403s urllib's default agent
        **({"Authorization": f"Bearer {key}"} if key else {})},
        data=json.dumps({"model": seat["model"], "max_tokens": max_tokens,  # reasoning models need room to answer
                         "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": metin}]}).encode())
    for deneme in (1, 2):  # connection timeouts happen in bursts; try once more, but not on an HTTP error
        try:
            with urllib.request.urlopen(istek, timeout=150) as r:
                cevap = (json.loads(r.read())["choices"][0]["message"]["content"] or "").strip()
            break
        except urllib.error.URLError as e:
            if deneme == 2 or isinstance(e, urllib.error.HTTPError):
                raise
    if not cevap:
        raise RuntimeError("empty answer")
    return cevap


def sor_hakem(tur2):
    sistem = T("Üyelerin son görüşünü oku; '(cevap yok' diye başlayanları sayma. Aynı seçeneği farklı sözlerle söyleyenleri "
               "birleştir. Tek satır yaz: '<kaç>/<cevap veren üye sayısı>: <seçenek>' (çoğunluk varsa) ya da "
               "'oy birliği yok: <kim ne dedi, kısa>'. Başka bir şey yazma.",
               "Read each member's final opinion; ignore ones starting with '(no answer'. Merge members who name the same "
               "option in different words. Write one line: '<count>/<members who answered>: <option>' (if there is a "
               "majority) or 'no majority: <who said what, briefly>'. Write nothing else.")
    if agents.has_chat_api():
        out = api_sor(C["chat_api"], sistem, tur2, max_tokens=300)
    else:
        out = agent_sor(C["agent"]["light_model"], sistem, tur2, timeout=120)
    if not out.strip():
        raise RuntimeError("empty verdict")
    return out.strip().splitlines()[0]


def herkes(fn):
    with ThreadPoolExecutor(len(UYELER)) as ex:
        isler = {u: ex.submit(fn, u) for u in UYELER}
    out = {}
    for u, f in isler.items():
        try:
            out[u] = f.result()
        except Exception as e:  # a seat that fails misses the round; the council goes on with the rest
            out[u] = (T("(cevap yok: ", "(no answer: ") + f"{e!r})")[:200]
    return out


def bos(c):
    return c.startswith(("(cevap yok", "(no answer"))


def gecmis_ornekler(n=3):
    """The last councils the owner gave a verdict on, so members see what the owner judged right."""
    if not KAYIT.exists():
        return ""
    satirlar = [json.loads(l) for l in KAYIT.read_text(encoding="utf-8").splitlines() if l.strip()]
    hukumlu = [s for s in satirlar if s.get("owner")][-n:]
    return "".join(f"\n- Q: {s['soru'][:150]} | Council: {s['karar'][:100]} | Owner: {s['owner'][:150]}" for s in hukumlu)


def konsey(soru):
    ornek = gecmis_ornekler()
    giris = soru + (T("\n\nSahibinin önceki konseylere verdiği hükümler (ölçütünü buradan öğren):",
                      "\n\nThe owner's verdicts on earlier councils (learn their criteria from these):") + ornek if ornek else "")
    t1 = herkes(lambda u: sor(u, giris))
    if len(UYELER) == 1:  # nothing to vote on
        return kaydet(soru, t1, {}, {}, T("tek koltuk, oylama yok", "single seat, no vote"), t1)
    ozet = "\n\n".join(f"[{u}]\n{c}" for u, c in t1.items())
    try:  # a unanimous first round gains nothing from a debate round (Debate or Vote, arXiv 2601.19921)
        karar = sor_hakem(ozet)
    except Exception:
        karar = ""
    n = sum(not bos(c) for c in t1.values())
    if n >= 3 and karar.startswith(f"{n}/{n}"):
        return kaydet(soru, t1, {}, {}, karar, t1)
    t2 = herkes(lambda u: sor(u, T(f"Soru: {soru}\n\nTur 1 görüşleri:\n{ozet}\n\nÖtekilerin en zayıf noktasını söyle, ikna "
                                   "olduysan fikrini değiştir. Son satırın tam olarak şu biçimde olsun: OY: EVET ya da OY: HAYIR "
                                   "ya da OY: <seçtiğin seçenek, en fazla 8 kelime>",
                                   f"Question: {soru}\n\nRound 1 opinions:\n{ozet}\n\nName the weakest point of the others; "
                                   "change your mind if convinced. Your last line must be exactly: VOTE: YES or VOTE: NO or "
                                   "VOTE: <the option you pick, at most 8 words>")))
    oylar = {u: (c.strip().splitlines() or [""])[-1].removeprefix("OY:").removeprefix("VOTE:").strip()[:80]
             for u, c in t2.items()}
    # votes are free text ("ship it" and "ship it this week" are the same vote); the judge does the counting
    try:
        karar = sor_hakem("\n\n".join(f"[{u}]\n{c}" for u, c in t2.items()))
    except Exception as e:
        karar = T("hakem yok", "no judge") + f" ({e!r}); " + " | ".join(f"{u}: {o}" for u, o in oylar.items())
    return kaydet(soru, t1, t2, oylar, karar, t2)


def kaydet(soru, t1, t2, oylar, karar, son):
    KAYIT.parent.mkdir(parents=True, exist_ok=True)
    with KAYIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"zaman": f"{datetime.now():%Y-%m-%d %H:%M}", "soru": soru, "tur1": t1, "tur2": t2,
                            "oylar": oylar, "karar": karar, "owner": ""}, ensure_ascii=False) + "\n")
    return "\n\n".join(f"[{u}] {c}" for u, c in son.items()) + T("\n\nKONSEY KARARI: ", "\n\nCOUNCIL VERDICT: ") + karar


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print(T("Kullanım: magi.py \"soru\"  (koltuklar: ", "Usage: magi.py \"question\"  (seats: ")
              + ", ".join(f"{u}={s.get('kind', 'agent')}" for u, s in UYELER.items()) + ")")
        sys.exit(0)
    soru = " ".join(sys.argv[1:]) or sys.stdin.read()
    print(konsey(soru.strip()))
