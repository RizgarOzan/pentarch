"""Live meeting assistant: transcribes the other side of a call (system audio: Meet, Zoom...) and optionally your
microphone, suggests questions to ask and a draft answer when you are asked something, and at the end writes the
transcript, your notes and a summary to the notes folder. Audio never touches the disk, only text.

Start:  python -I pentarch.py meeting ["title"]      Page: http://127.0.0.1:<meeting.port>
The goal comes from config meeting.goal, else <home>/gorusme.md. Needs: pip install soundcard numpy faster-whisper
(soundcard's loopback capture works on Windows; other systems need a monitor source).
"""
import json
import re
import site
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.append(site.getusersitepackages())  # these packages are often pip --user installed; -I hides that folder
from config import C, HOME, LANG_NAME, NOTES, OWNER, T  # noqa: E402

SR = 16000
BLOCK = SR // 2  # 0.5 s
AUTOSAVE = HOME / "gorusme-son.txt"  # text only, survives a crash
YOU, THEM = T("Sen", "You"), T("Karşı", "Them")
# whisper writes these into silence or music
HALLUCINATIONS = {"thank you.", "thank you", "thanks for watching!", "thank you for watching.", "you", ".", "bye.",
                  "altyazı m.k.", "izlediğiniz için teşekkürler."}

lock = threading.Lock()
state = {"lines": [], "sorular": [], "soru": "", "cevap": "", "notlar": "", "durum": T("dinliyor", "listening"),
         "bitti": False}
stop = threading.Event()
force = threading.Event()
simdi = threading.Event()  # the "suggest now" button: do not wait for the other side to finish
last_remote = [0.0]
pending = [0]  # chunks still being transcribed
TURN_GAP = 6  # s: chunks of the same speaker closer than this are one turn (a question cut by a breath or the 15 s limit)
DONE_QUIET = 1.5  # s of silence from the other side before their turn counts as finished
_model = []


def hedef():
    """The meeting goal: config meeting.goal, else <home>/gorusme.md, else empty."""
    if C["meeting"].get("goal"):
        return C["meeting"]["goal"]
    f = HOME / "gorusme.md"
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


def transcribe(samples):
    if not _model:
        from faster_whisper import WhisperModel
        _model.append(WhisperModel(C["whisper"]["model"], device="cpu", compute_type="int8"))
    segs, _ = _model[0].transcribe(samples, language=C["whisper"].get("language") or None, vad_filter=True)
    return " ".join(s.text.strip() for s in segs)


def add_line(who, text):
    t = text.strip()
    if not t or t.lower() in HALLUCINATIONS:
        return
    with lock:
        son = state["lines"][-1] if state["lines"] else None
        if son and son["kim"] == who and time.time() - son["ts"] < TURN_GAP:
            son["metin"], son["ts"] = son["metin"] + " " + t, time.time()  # same turn, keep the question in one piece
        else:
            state["lines"].append({"ts": time.time(), "t": f"{datetime.now():%H:%M:%S}", "kim": who, "metin": t})
        dump = "\n".join(f"[{x['t']}] {x['kim']}: {x['metin']}" for x in state["lines"])
    AUTOSAVE.write_text(dump, encoding="utf-8")
    if who == THEM:  # suggest right after the other side speaks
        force.set()


def listen(np, mic, who):
    """Cuts a chunk when speech stops (2 quiet blocks) or after 15 s and transcribes it in the background."""
    floor, buf, quiet = 0.002, [], 0
    with mic.recorder(samplerate=SR, channels=1, blocksize=1024) as rec:
        while not stop.is_set():
            d = rec.record(numframes=BLOCK)[:, 0]
            rms = float(np.sqrt((d ** 2).mean()))
            speech = rms > max(0.006, floor * 3)
            if who == THEM and speech:
                last_remote[0] = time.time()
            if who == YOU and speech and time.time() - last_remote[0] < 0.6:
                speech = False  # the other side leaking from the speakers into the microphone
            if not speech:
                floor = 0.95 * floor + 0.05 * rms
            if speech or buf:
                buf.append(d)
                quiet = 0 if speech else quiet + 1
            if buf and (quiet >= 2 or len(buf) >= 30):
                chunk, buf, quiet = np.concatenate(buf).astype(np.float32), [], 0
                if len(chunk) >= SR:  # under a second: a cough, a click
                    def work(c=chunk):
                        try:
                            add_line(who, transcribe(c))
                        finally:
                            with lock:
                                pending[0] -= 1
                    with lock:
                        pending[0] += 1
                    threading.Thread(target=work, daemon=True).start()


def sor(sistem, metin, timeout=90):
    """A cheap one-shot answer: chat endpoints when configured (personal data rules apply), else the agent CLI."""
    import agents
    import magi
    if agents.has_chat_api():
        try:
            return agents.chat([{"role": "system", "content": sistem}, {"role": "user", "content": metin}],
                               timeout=timeout, kisisel=True)
        except Exception as e:
            print(T("uç nokta olmadı, ajan CLI'ye geçiyorum:", "endpoint failed, using the agent CLI:"), e, file=sys.stderr)
    return magi.agent_sor(C["agent"]["fast_model"], sistem, metin, timeout=timeout)


def oneri_sistemi():
    return T(
        f"Canlı bir görüşmede {OWNER}'a fısıldayan asistansın. Yalnız JSON döndür: "
        '{"soru": "...", "tamam": true, "sorular": ["...", "..."], "cevap": "..."}. soru: karşı tarafın SON sorusu, '
        "nerede başlayıp nerede bittiğini sen bul: giriş cümlelerini, önceki sorunun kalıntısını ve sohbet dolgusunu "
        "at, soru birkaç satıra bölünmüşse birleştir, birden fazla parçası varsa hepsini yaz, bariz transkript "
        f"hatalarını düzelt. {OWNER} o soruyu zaten cevapladıysa ya da soru yoksa boş string. tamam: son cümle "
        "yarıda kesilmiş görünüyorsa false. sorular: ŞİMDİ sorulabilecek 1-2 kısa soru, karşı tarafın az önce "
        "söylediğine bağlı ve gerçek merak taşıyan; sorulmuş olanı tekrar etme. cevap: soru doluysa yalnız o soruya, "
        f"her parçasına, {OWNER}'ın ağzından 1-3 cümlelik sade, konuşma dilinde cevap; yoksa boş string. Görüşmenin "
        "dilinde yaz. Abartma, uydurma bilgi koyma.",
        f"You whisper to {OWNER} during a live call. Return JSON only: "
        '{"soru": "...", "tamam": true, "sorular": ["...", "..."], "cevap": "..."}. soru: the other side\'s LAST '
        "question; find where it starts and ends yourself: drop lead-in sentences, leftovers of the previous question "
        "and small talk, join it if it is split over several lines, keep every part if it has more than one, fix "
        f"obvious transcript errors. Empty string if {OWNER} already answered it or nothing was asked. tamam: false "
        "if the last sentence looks cut off. sorular: 1-2 short questions to ask NOW, tied to what the other "
        "side just said and showing real curiosity; never repeat one already asked. cevap: if soru is not empty, a "
        f"plain spoken 1-3 sentence answer to that question only, covering each part, in {OWNER}'s voice; otherwise "
        "an empty string. Write in the language of the call. No exaggeration, no invented facts.")


def suggester(amac):
    seen = 0
    while not stop.is_set():
        force.wait(20)
        force.clear()
        # the other side may still be mid-question: wait until they go quiet and every chunk is transcribed
        while not stop.is_set() and not simdi.is_set() and (time.time() - last_remote[0] < DONE_QUIET or pending[0]):
            time.sleep(0.2)
        simdi.clear()
        force.clear()
        if stop.is_set():
            break
        with lock:
            n = sum(len(x["metin"]) for x in state["lines"])  # a merged turn grows without adding a line
            recent = [x for x in state["lines"] if x["ts"] >= time.time() - 120] or state["lines"][-6:]
            asked = [x["metin"] for x in state["lines"] if x["kim"] == YOU and "?" in x["metin"]][-8:]
        if n == seen:
            continue
        seen = n
        tx = "\n".join(f"{x['kim']}: {x['metin']}" for x in recent)
        try:
            with lock:
                state["durum"] = T("öneri hazırlanıyor", "preparing a suggestion")
            out = sor(oneri_sistemi(), T(f"Görüşme amacı:\n{amac}\n\nZaten sorulanlar: {asked}\n\nSon 2 dk ({YOU}={OWNER}, {THEM}=karşı taraf):\n{tx}",
                                         f"Meeting goal:\n{amac}\n\nAlready asked: {asked}\n\nLast 2 min ({YOU}={OWNER}, {THEM}=the other side):\n{tx}"))
            js = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
            with lock:
                state["sorular"] = [str(q) for q in js.get("sorular", [])][:2]
                if js.get("cevap"):
                    state["cevap"] = str(js["cevap"])
                    state["soru"] = str(js.get("soru") or "") + (
                        "" if js.get("tamam", True) else T(" … (yarım olabilir)", " … (may be cut off)"))
        except Exception as e:
            print(T("öneri hatası:", "suggestion error:"), e, file=sys.stderr)
        with lock:
            state["durum"] = T("dinliyor", "listening")


def slug(s):
    return re.sub(r"[^\w-]+", "-", s.casefold()).strip("-")[:60] or T("gorusme", "meeting")


def finish(amac, baslik):
    """Writes NOTES/gorusme-<title>-<date>.md once and returns its name."""
    with lock:
        if state["bitti"]:
            return state.get("sayfa", "")
        state["bitti"], state["durum"] = True, T("özet yazılıyor", "writing the summary")
        lines, notes = list(state["lines"]), state["notlar"]
    stop.set()
    force.set()
    tx = "\n".join(f"[{x['t']}] {x['kim']}: {x['metin']}" for x in lines)
    try:
        ozet = sor(T(f"Görüşme özetçisisin. {LANG_NAME} dilinde düz cümlelerle yaz: önce 3-6 cümlelik özet, sonra "
                     "'Öğrenilenler' ve 'Sonraki adımlar' başlıklarıyla kısa paragraflar. Yalnız transkriptte geçeni yaz.",
                     f"You summarise meetings. Write plain sentences in {LANG_NAME}: a 3-6 sentence summary first, then "
                     "short paragraphs under 'What I learned' and 'Next steps'. Only what the transcript says."),
                   f"{T('Amaç', 'Goal')}:\n{amac}\n\n{T('Notlar', 'Notes')}:\n{notes}\n\n{T('Transkript', 'Transcript')}:\n{tx[-60000:]}",
                   timeout=240)
    except Exception as e:
        ozet = T(f"(özet çıkarılamadı: {e})", f"(no summary: {e})")
    day = f"{datetime.now():%Y-%m-%d}"
    NOTES.mkdir(parents=True, exist_ok=True)
    page = NOTES / f"gorusme-{slug(baslik)}-{day}.md"
    page.write_text(
        f"# {T('Görüşme', 'Meeting')}: {baslik or '-'} ({day})\n\n{T('Amaç', 'Goal')}: {(amac.splitlines() or ['-'])[0]}\n\n"
        f"## {T('Özet', 'Summary')}\n\n{ozet}\n\n## {T('Notlar', 'Notes')}\n\n{notes or '-'}\n\n"
        f"## {T('Transkript', 'Transcript')}\n\n{T(f'{YOU} = mikrofon, {THEM} = sistem sesi. Whisper çevirisi, hatalı kelime olabilir.', f'{YOU} = microphone, {THEM} = system audio. Whisper transcript, may contain wrong words.')}\n\n"
        f"{tx or '-'}\n", encoding="utf-8")
    with lock:
        state["durum"], state["sayfa"] = T(f"kaydedildi: {page.name}", f"saved: {page.name}"), page.name
    return page.name


def page_html():
    return ("""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width"><title>%s</title>
<style>
body{margin:0;font:15px/1.45 system-ui,sans-serif;background:#111;color:#ddd;display:grid;grid-template:auto 1fr 84px/1fr;height:100vh}
#tx{grid-row:2;overflow:auto;padding:8px 14px;font-size:13px;color:#999}#tx p{margin:4px 0}small{color:#666;margin-right:6px}
#side{grid-row:1;padding:10px 14px;font-size:17px;border-bottom:1px solid #333}
h3{margin:6px 0;font-size:13px;color:#888;text-transform:uppercase;letter-spacing:.05em}
.q{background:#1d2a33;padding:8px 10px;margin:6px 0;border-radius:6px}#cv{background:#2a2219;padding:8px 10px;border-radius:6px;min-height:40px;font-size:18px}
#bot{grid-row:3;display:flex;gap:8px;padding:8px;border-top:1px solid #333}
textarea{flex:1;background:#1a1a1a;color:#ddd;border:1px solid #333;font:inherit;padding:8px}
button{background:#333;color:#ddd;border:0;padding:8px 14px;cursor:pointer}#st{color:#888;font-size:12px}
</style>
<div id=tx></div>
<div id=side><div id=st></div><h3>%s</h3><div id=qs></div><button onclick="fetch('/simdi',{method:'POST'})">%s</button>
<h3>%s</h3><div id=sr style="color:#9bd;font-size:14px;margin-bottom:6px"></div><div id=cv></div></div>
<div id=bot><textarea id=nt placeholder="%s"></textarea><div><button onclick="bitir()">%s</button></div></div>
<script>
let n=-1,tm;const nt=document.getElementById('nt'),esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
nt.oninput=()=>{clearTimeout(tm);tm=setTimeout(()=>fetch('/not',{method:'POST',body:nt.value}),600)};
async function bitir(){const r=await fetch('/bitir',{method:'POST',body:nt.value});document.getElementById('st').textContent=await r.text()}
async function tick(){try{const s=await(await fetch('/durum')).json();
 if(s.lines.length!=n){n=s.lines.length;const tx=document.getElementById('tx');const end=tx.scrollTop+tx.clientHeight>=tx.scrollHeight-30;
  tx.innerHTML=s.lines.map(l=>`<p><small>${l.t}</small><b>${esc(l.kim)}:</b> ${esc(l.metin)}</p>`).join('');if(end)tx.scrollTop=tx.scrollHeight}
 document.getElementById('qs').innerHTML=s.sorular.map(q=>`<div class=q>${esc(q)}</div>`).join('');
 document.getElementById('sr').textContent=s.soru;document.getElementById('cv').textContent=s.cevap;document.getElementById('st').textContent=s.durum}catch(e){}}
setInterval(tick,1500);tick();
</script>""" % (T("Görüşme", "Meeting"), T("Şimdi sorulacak", "Ask now"), T("Şimdi öner", "Suggest now"),
                 T("Cevap taslağı", "Draft answer"), T("Notların (kendiliğinden kaydedilir)", "Your notes (saved as you type)"),
                 T("Bitir ve kaydet", "Finish and save")))


def serve(port, amac, baslik):
    html = page_html()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, body, ctype="text/plain; charset=utf-8"):
            b = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == "/durum":
                with lock:
                    return self.send(json.dumps(state, ensure_ascii=False), "application/json")
            self.send(html, "text/html; charset=utf-8")

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
            if self.path in ("/not", "/bitir"):
                with lock:
                    state["notlar"] = body
            if self.path == "/simdi":
                simdi.set()
                force.set()
            if self.path == "/bitir":
                return self.send(finish(amac, baslik))
            self.send("ok")

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)  # local only: the transcript is private
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main(baslik=""):
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        import numpy as np
        import soundcard as sc
    except ImportError as e:
        print(T(f"Görüşme asistanı için gerekenler eksik ({e.name}): pip install soundcard numpy faster-whisper",
                f"The meeting assistant needs more packages ({e.name}): pip install soundcard numpy faster-whisper"))
        return 1
    amac = hedef()
    spk = sc.default_speaker()
    kaynaklar = [(sc.get_microphone(spk.name, include_loopback=True), THEM)]
    if C["meeting"].get("mic", True):
        kaynaklar.insert(0, (sc.default_microphone(), YOU))
    for mic, who in kaynaklar:
        threading.Thread(target=listen, args=(np, mic, who), daemon=True).start()
    threading.Thread(target=suggester, args=(amac,), daemon=True).start()
    port = int(C["meeting"].get("port") or 8765)
    serve(port, amac, baslik)
    url = f"http://127.0.0.1:{port}"
    print(T(f"sistem sesi: {spk.name} | sayfa: {url} | bitirmek için sayfadaki düğme ya da Ctrl+C",
            f"system audio: {spk.name} | page: {url} | finish with the page button or Ctrl+C"))
    webbrowser.open(url)
    try:
        while not state.get("sayfa"):
            time.sleep(0.5)
        time.sleep(2)  # let the page read the saved name
    except KeyboardInterrupt:
        print(T("kaydediliyor:", "saving:"), finish(amac, baslik))
    return 0


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:])))
