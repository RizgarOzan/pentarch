"""Pentarch end-to-end tests (2026-11-03).

Ölçüt τ-bench'ten (arxiv 2406.12045): sonucu cevap metninden değil bıraktığı durumdan yargıla, güvenilirliği pass^k
ile ölç (aynı iş k denemenin hepsinde geçmeli). Hiçbir şey yapmayan ajanın geçemeyeceği testler yaz (arxiv 2507.02825).

  python -I tests/e2e.py           # A: fake Telegram/brain, free, ~20 s
  python -I tests/e2e.py --canli   # A + B: a real run with a separate sonnet brain (pass^3), a few cents, ~2 min
Never touches a real runtime home: PENTARCH_HOME is set to a fresh temp folder before app/ is imported, and nothing
is written to Telegram.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import date
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="pentarch-e2e-"))
os.environ["PENTARCH_HOME"] = str(TMP)  # before any app/ import: config.py reads it once
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
sys.stdout.reconfigure(encoding="utf-8")
import beyin  # noqa: E402
import magi  # noqa: E402
import pentarch as U  # noqa: E402

U.note = lambda m: None  # keep the test's fake cancellations out of pentarch.log
sonuclar = []


def test(fn):
    t0 = time.monotonic()
    try:
        fn()
        sonuclar.append((fn.__name__, True, ""))
    except Exception as e:
        sonuclar.append((fn.__name__, False, f"{e!r}"[:300]))
    print(f"{'GEÇTİ' if sonuclar[-1][1] else 'KALDI'}  {fn.__name__} ({time.monotonic() - t0:.1f} sn) {sonuclar[-1][2]}")
    return fn


# --- A: kuralsal, bedava -------------------------------------------------------

def kuyruk_sirasi_ve_yarim_kalmama():
    """Messages arriving during a run are not lost, are handled in order as one batch, the owner is told the job is
    still running, and the queue file is cleaned up."""
    U.BEKLEYEN = TMP / "gelen_kuyruk.json"
    gonderilen, islenen = [], []
    U.send = lambda t, buttons=None: gonderilen.append(t)
    U.tg.log = lambda *a, **k: None
    U.tg.save_state = lambda s: None
    U.note = lambda m: None
    U.state.update({"offset": 0, "chat_id": 1})

    def yavas_ask(texts, source="Telegram"):
        with U.main_lock:
            U.active_runs["k"] = {"kind": "telegram", "zaman": U.now(), "is": "x"}
            islenen.append(list(texts))
            time.sleep(2)
            U.active_runs.pop("k", None)
    U.ask = yavas_ask
    partiler = [[{"update_id": i, "message": {"chat": {"id": 1}, "message_id": i, "text": t}}]
                for i, t in enumerate(["ilk", "ikinci", "üçüncü"], 1)]

    def api(method, **kw):
        if method == "getUpdates":
            time.sleep(0.4)
            if partiler:
                return partiler.pop(0)
            time.sleep(3600)
        return {}
    U.tg.api = api
    U.message_text = lambda m: m["text"]
    threading.Thread(target=U.telegram_worker, daemon=True).start()
    threading.Thread(target=U.poll_telegram, daemon=True).start()
    time.sleep(1)
    ara = json.loads(U.BEKLEYEN.read_text(encoding="utf-8"))
    assert ara == ["ilk", "ikinci"], f"diskteki kuyruk: {ara}"
    time.sleep(6)
    assert islenen == [["ilk"], ["ikinci", "üçüncü"]], f"işlenen: {islenen}"
    assert any(U.T("sürüyor", "Still on") in g for g in gonderilen), f"gönderilen: {gonderilen}"
    assert not U.BEKLEYEN.exists(), "kuyruk dosyası temizlenmedi"


def kuyruk_dosyasi_baska_dosyayla_cakismaz():
    """2026-11-03: the queue was first written to bekleyen.json and wiped the owner's awaiting-reply list."""
    kuyruk = U.BEKLEYEN.name
    assert kuyruk != U.PENDING.name, f"kuyruk dosyası cevap-bekleyen listesiyle aynı: {kuyruk}"
    ayni = [p.name for p in U.HOME.glob("*.json") if p.name == kuyruk and p != U.BEKLEYEN]
    assert not ayni, ayni


def iptal_kosan_beyni_durdurur():
    class Sahte:
        iptal = yenileniyor = False
        lock = threading.Lock()
        olduruldu = False
        def _alive(self): return True
        def _kill(self): self.olduruldu = True
    B = Sahte()
    U.BEYINLER.clear()
    U.BEYINLER["hizli"] = B
    bos = U.T("Şu an", "Nothing")
    assert U.iptal().startswith(bos), "boşta 'koşan iş yok' demeli"
    with B.lock:
        B.yenileniyor = True  # background session refresh: must not be cut, the owner still gets a reply
        assert U.iptal().startswith(bos) and not B.olduruldu and not B.iptal, "arka yenileme kesildi"
        B.yenileniyor = False
        assert U.iptal() == "" and B.olduruldu and B.iptal
    U.BEYINLER.clear()


def yonlendirme_fazla_dusunmez():
    """Gündelik mesaj opus'a gitmemeli; açık analiz isteği gitmeli. 6 kelimeden kısa olanlar haiku'ya da sorulmaz."""
    eski, U.ayar = U.ayar, lambda k: {"derin_mod": "otomatik"}.get(k)
    hizli = ["selam", "nasılsın", "bir fikir: yarın ara", "şunu incele", "github yıldız kaç", "tamam devam"]
    derin = ["iki mimariyi karşılaştır", "bunu analiz et", "yeni proje öner bana", "planla bunu"]
    try:
        for m in hizli:
            assert not U.derin_mi(m), f"hızlı olmalıydı: {m}"
        for m in derin:
            assert U.derin_mi(m), f"derin olmalıydı: {m}"
    finally:
        U.ayar = eski


def beyin_kill_cocuklari_da_oldurur():
    """claude.CMD -> cmd.exe -> node: eskiden yalnız cmd ölüyor, node yetim kalıyordu."""
    B = beyin.Beyin(log=lambda m: None)
    B.proc = subprocess.Popen(["cmd", "/c", "ping -n 60 127.0.0.1 >NUL"], creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(1)
    cocuk = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={B.proc.pid}').ProcessId"],
                           capture_output=True, text=True).stdout.split()
    assert cocuk, "çocuk süreç açılmadı"
    B._kill()
    time.sleep(1)
    kalan = subprocess.run(["tasklist", "/FI", f"PID eq {cocuk[0]}"], capture_output=True, text=True).stdout
    assert cocuk[0] not in kalan, f"çocuk {cocuk[0]} hâlâ yaşıyor"


def yenileme_cevaptan_sonra():
    """2026-11-04: opus ilk turda 60k'yı aşıyor, her mesaj cevaptan önce özet + yeni süreç bekliyordu (+9-19 sn)."""
    olay = []

    class Sahte(beyin.Beyin):
        def _start(self): self.proc, self.ctx, self.turns = object(), 0, 0; olay.append("başla")
        def _alive(self): return self.proc is not None
        def _kill(self): self.proc = None
        def _send(self, text, timeout):
            if text == beyin.SUMMARY_ASK:
                time.sleep(0.5)
                olay.append("özet")
                return {"result": "özet"}
            olay.append(("cevap", text))
            self.ctx, self.turns, self.last_used = 200_000, self.turns + 1, time.monotonic()
            return {"result": "tamam"}
    B = Sahte("opus", log=lambda m: None)
    B.ask("bir")
    assert olay == ["başla", ("cevap", "bir")], f"cevaptan önce yenilendi: {olay}"
    time.sleep(1)
    assert olay[2:] == ["özet", "başla"], f"cevaptan sonra arkada yenilenmedi: {olay}"
    B.ask("iki")
    assert olay[-1] == ("cevap", "(Önceki konuşmanın özeti: özet)\n\niki"), f"özet yeni oturuma geçmedi: {olay[-1]}"


def magi_koltuk_duserse_konsey_surer():
    """A seat that raises (quota, timeout) misses the round; the council goes on and the verdict still comes out."""
    cagrilar = []

    def agent_sahte(model, sistem, metin, timeout=300):
        cagrilar.append(model)
        if model == "dusen":
            raise RuntimeError("status: 429 limit exceeded")
        return "A seçeneği.\nOY: A"

    def api_sahte(seat, sistem, metin, max_tokens=4000):  # API seats must not go out to the network
        cagrilar.append(seat["model"])
        return "A seçeneği.\nOY: A"
    uyeler = {"BILIM": {"kind": "agent", "model": "m1", "role": "r"},
              "KORUYUCU": {"kind": "agent", "model": "m2", "role": "r"},
              "HIRS": {"kind": "openai", "model": "api1", "base_url": "http://127.0.0.1:9", "role": "r"},
              "UYGULAYICI": {"kind": "openai", "model": "api2", "base_url": "http://127.0.0.1:9", "role": "r"},
              "SUPHECI": {"kind": "agent", "model": "dusen", "role": "r"}}
    eski = magi.agent_sor, magi.api_sor, magi.sor_hakem, magi.KAYIT, magi.UYELER
    magi.agent_sor, magi.api_sor, magi.UYELER = agent_sahte, api_sahte, uyeler
    magi.KAYIT = TMP / "magi.jsonl"
    karar = magi.T("KONSEY KARARI", "COUNCIL VERDICT")
    try:
        magi.sor_hakem = lambda t: "3/4: A"  # ilk turda oy birliği yok: iki tur
        out = magi.konsey("A mı B mi?")
        assert f"{karar}: 3/4: A" in out and "[SUPHECI] " + magi.T("(cevap yok", "(no answer") in out, out
        assert len(cagrilar) == 10 and cagrilar.count("dusen") == 2, f"iki turda da her koltuk sorulmalıydı: {cagrilar}"
        assert cagrilar.count("api1") == cagrilar.count("api2") == 2, f"API koltukları api_sor'a gitmeli: {cagrilar}"
        cagrilar.clear()
        magi.sor_hakem = lambda t: "4/4: A"  # cevap veren 4 üyede oy birliği: tartışma turu atlanır
        out = magi.konsey("A mı B mi?")
        assert f"{karar}: 4/4: A" in out and len(cagrilar) == 5, f"oy birliğinde tek tur olmalıydı: {cagrilar}"
        kayit = [json.loads(l) for l in magi.KAYIT.read_text(encoding="utf-8").splitlines()]
        assert len(kayit) == 2 and all(k["owner"] == "" for k in kayit), kayit
    finally:
        magi.agent_sor, magi.api_sor, magi.sor_hakem, magi.KAYIT, magi.UYELER = eski


def panel_hizli_cevap_verir():
    """The panel of the code under test, started on a free port in the temp home; the page must load fast."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        U.PANEL_PORT = s.getsockname()[1]
    threading.Thread(target=U.serve_panel, daemon=True).start()
    time.sleep(0.5)
    t0 = time.monotonic()
    req = urllib.request.Request(f"http://127.0.0.1:{U.PANEL_PORT}/", headers={"Host": f"127.0.0.1:{U.PANEL_PORT}"})
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
    assert time.monotonic() - t0 < 2, f"panel yavaş: {time.monotonic() - t0:.1f} sn"


# --- B: canlı model, pass^3 --------------------------------------------------

def canli_pass3():
    """A separate sonnet/low brain (the same settings as the live assistant's). Her iş 3 kez; cevap dosyadan/saatten doğrulanır,
    her cevap 60 sn içinde ve boş değil (yarım kalmadı)."""
    isler = [
        (f"{U.AYARLAR} dosyasında derin_efor değeri ne? Yalnız değeri yaz.",
         lambda c: json.loads((U.HOME / "ayarlar.json").read_text(encoding="utf-8"))["derin_efor"] in c.lower()),
        ("Bugünün tarihi ne? Yalnız YYYY-MM-DD yaz.", lambda c: date.today().isoformat() in c),
        ("17 ile 23'ü çarp, yalnız sayıyı yaz.", lambda c: "391" in c),
    ]
    U.ayar("derin_efor")  # writes the temp home's ayarlar.json with defaults
    B = beyin.Beyin("sonnet", "low", log=lambda m: None)
    try:
        for soru, dogru in isler:
            for k in range(3):
                B.rotate(summarize=False)  # her deneme temiz oturum; öncekinin cevabını kopyalamasın
                t0 = time.monotonic()
                out = B.ask(soru, timeout=120)
                sure, cevap = time.monotonic() - t0, (out.get("result") or "").strip()
                assert cevap, f"boş cevap ({soru[:30]}, deneme {k + 1})"
                assert dogru(cevap), f"yanlış: {soru[:30]} -> {cevap[:80]} (deneme {k + 1})"
                assert sure < 60, f"yavaş: {sure:.0f} sn ({soru[:30]})"
    finally:
        B.close()


if __name__ == "__main__":
    for fn in (kuyruk_dosyasi_baska_dosyayla_cakismaz, iptal_kosan_beyni_durdurur, yonlendirme_fazla_dusunmez,
               beyin_kill_cocuklari_da_oldurur, yenileme_cevaptan_sonra, magi_koltuk_duserse_konsey_surer, panel_hizli_cevap_verir,
               kuyruk_sirasi_ve_yarim_kalmama):
        test(fn)
    if "--canli" in sys.argv:
        test(canli_pass3)
    gecen = sum(ok for _, ok, _ in sonuclar)
    print(f"\n{gecen}/{len(sonuclar)} geçti")
    sys.exit(0 if gecen == len(sonuclar) else 1)
