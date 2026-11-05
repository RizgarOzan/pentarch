"""Chat brain: one long-lived `claude -p` process (stream-json). The same process carries the conversation instead of
starting one per message, so the prompt cache stays warm and there is no cold start. When the context passes MAX_CTX
(after a reply, in the background) or the process idles for IDLE, the session is renewed with a short summary.

Other agent CLIs have no persistent mode; for them `Tek` runs one headless call per message with recent context."""
import json
import os
import queue
import shutil
import subprocess
import threading
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402
from config import C, EXTRA_DIRS, HOME, NOTES, OWNER  # noqa: E402

RULES = HOME / "kurallar.md"
WIKI = NOTES
CLAUDE = shutil.which("claude") or "claude"
# Gmail/Takvim/Chrome/skill yok: bunlar MCP ve eklenti yükü getiriyor (ölçüm 2026-11-02: 48k → 14k token/tur).
# Gerekince model `AGIR:` der, pentarch.py işi tam donanımlı oturuma verir.
TOOLS = "Bash,Read,Edit,Write,Grep,Glob,WebFetch,WebSearch,Agent"
# Masaüstü (Windows-MCP: ekran okuma, tıklama, yazma; PowerShell/Registry/dosya/süreç araçları kapalı). Tur başına
# +5k token, çoğu önbellekten. Yalnız config desktop_control açıksa yüklenir.
MASAUSTU = HOME / "masaustu-mcp.json"
# opus ilk turda 60k'yı aşıyordu; her mesaj cevaptan önce özet + yeni süreç bekliyordu (+9-19 sn, 2026-11-04)
MAX_CTX = {"opus": 120_000, "sonnet": 120_000}  # model -> sınır; yoksa 60k
IDLE = 55 * 60  # abonelikte önbellek 1 saat yaşar; sonrası zaten soğuk
SUMMARY_ASK = (f"[System] This session is closing and will hand over to a new one. In at most 120 words of plain text, "
               f"summarize everything needed to continue the conversation with {OWNER}: topic, open tasks, promises you "
               f"made, {OWNER}'s decisions. Write nothing else.")


class Beyin:
    def __init__(self, model="sonnet", effort="low", log=print, ilk=None):
        self.model, self.effort, self.log = model, effort, log
        self.ilk = ilk  # yeni oturumun ilk mesajına eklenecek çekirdek hafızayı döndüren işlev
        self.gorulen = set()  # bu oturumda hafıza aramasının verdiği parçalar (hafiza.bagla tekrar vermesin)
        self.proc = None
        self.lock = threading.Lock()
        self.events = queue.Queue()
        self.last_used = 0.0
        self.ctx = 0  # son API çağrısının bağlam boyu
        self.turns = 0
        self.summary = ""
        self.cwd = WIKI
        self.ofset = 0  # konusma.log'un bu oturumun gördüğü yeri (bayt); pentarch.py arada geçeni ekler

    def _args(self):
        args = [CLAUDE, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--model", self.model, "--effort", self.effort, "--permission-mode", C["agent"]["permission_mode"],
                "--strict-mcp-config", "--setting-sources", "", "--tools", TOOLS,
                "--append-system-prompt-file", str(RULES)]
        if C["agent"]["permission_mode"] != "bypassPermissions":
            args += ["--allowedTools", ",".join(C["agent"]["allowed_tools"])]
        if C["desktop_control"] and MASAUSTU.exists():
            args += ["--mcp-config", str(MASAUSTU)]
        for d in EXTRA_DIRS:
            args += ["--add-dir", str(d)]
        return args

    def _start(self):
        self.proc = subprocess.Popen(self._args(), cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     env={**os.environ, "CLAUDE_CODE_FORK_SUBAGENT": "0"},  # fork alt ajan bütün oturumu kopyalar
                                     stderr=open(HOME / "beyin.err", "a", encoding="utf-8"), encoding="utf-8",
                                     errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        self.events = queue.Queue()
        threading.Thread(target=self._read, args=(self.proc, self.events), daemon=True).start()
        self.ctx = self.turns = 0
        self.gorulen = set()
        self.log(f"beyin: yeni süreç ({self.model}, {self.effort})")

    @staticmethod
    def _read(proc, events):
        for line in proc.stdout:
            try:
                events.put(json.loads(line))
            except json.JSONDecodeError:
                pass
        events.put(None)  # süreç bitti

    def _alive(self):
        return self.proc is not None and self.proc.poll() is None

    def _send(self, text, timeout):
        self.proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                ev = self.events.get(timeout=max(1, deadline - time.monotonic()))
            except queue.Empty:
                self._kill()
                raise TimeoutError(f"beyin {timeout} sn içinde cevap vermedi")
            if ev is None:
                raise RuntimeError("beyin süreci beklenmedik şekilde kapandı, ayrıntı beyin.err")
            if ev.get("type") == "assistant":
                u = ev.get("message", {}).get("usage") or {}
                self.ctx = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")) or self.ctx
            elif ev.get("type") == "result":
                self.turns += 1
                self.last_used = time.monotonic()
                return ev

    def _kill(self):
        if self._alive():  # claude.CMD -> cmd.exe -> node: yalnız cmd ölürse node yetim kalıp çalışıyordu (2026-11-03)
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        self.proc = None

    def rotate(self, summarize=True):
        """Oturumu kapatır; istenirse önce kısa özet alıp yeni oturumun ilk mesajına ekler."""
        if summarize and self._alive() and self.turns:
            try:
                self.summary = (self._send(SUMMARY_ASK, 120).get("result") or "").strip()
            except Exception as e:
                self.log(f"beyin: özet alınamadı ({e!r})")
        elif not summarize:
            self.summary = ""
        self._kill()

    def ask(self, text, timeout=900, ek=None):
        """Mesajı sürekli oturuma verir, stream-json `result` olayını döndürür (pentarch.spend ile uyumlu alanlar).
        `ek(gorulen)` mesajın sonuna eklenecek hafıza bloğunu döndürür; oturum yenilendikten sonra çağrılır."""
        with self.lock:
            if self._alive() and self.turns and time.monotonic() - self.last_used > IDLE:  # önbellek soğuk; arkada açılmış boş süreç kalır
                self.log(f"beyin: oturum yenileniyor (boşta, bağlam {self.ctx // 1000}k, {self.turns} tur)")
                self.rotate()
            if not self._alive():
                self._start()
            if not self.turns:  # yeni oturumun ilk mesajı (süreç arkada önceden açılmış olabilir)
                if self.summary:
                    text = f"(Önceki konuşmanın özeti: {self.summary})\n\n{text}"
                    self.summary = ""
                if self.ilk:
                    text = f"{self.ilk()}\n\n{text}"
            if ek:
                text += ek(self.gorulen)
            out = self._send(text, timeout)
            if self.ctx > MAX_CTX.get(self.model, 60_000):  # yenileme cevaptan sonra, arkada; sıradaki mesaj özet beklemesin
                threading.Thread(target=self._arkada_yenile, daemon=True).start()
            return out

    def _arkada_yenile(self):
        with self.lock:
            if self._alive() and self.ctx > MAX_CTX.get(self.model, 60_000):  # araya giren mesaj yenilediyse tekrar etme
                self.log(f"beyin: oturum yenileniyor (bağlam {self.ctx // 1000}k, {self.turns} tur)")
                self.yenileniyor = True  # iptal bunu kesmesin: cevap bekleyen yok, kesilirse sahibine hiç dönüş olmuyordu
                try:
                    self.rotate()
                    self._start()
                finally:
                    self.yenileniyor = False

    def close(self):
        with self.lock:
            self._kill()


class Kucuk(Beyin):
    """Süzgeç, kısaltıcı gibi tek atımlık Haiku işleri için sürekli açık süreç: araçsız, kuralsız, kendi sistem
    istemiyle. Her seferinde `claude -p` açmak 9,6 sn sürüyordu, ~6 sn'si açılış (ölçüm 2026-11-03). Sorular birbirinden
    bağımsız; önceki cevaplar yönlendirmesin ve bağlam büyümesin diye TUR soruda bir süreç yenilenir, özet alınmaz."""
    TUR = 10

    def __init__(self, sistem, log=print):
        super().__init__(model=C["agent"]["light_model"] or "haiku", log=log)
        self.sistem, self.cwd = sistem, HOME  # wiki'de açılırsa oradaki CLAUDE.md'yi de yükleyebilir

    def _args(self):
        return [CLAUDE, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--model", self.model, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
                "--disable-slash-commands", "--no-session-persistence", "--system-prompt", self.sistem]

    def sor(self, text, timeout=60):
        if agents.has_chat_api():  # ayarlıysa ucuz uç nokta; claude süreci hiç açılmaz
            return {"result": agents.chat([{"role": "system", "content": self.sistem},
                                           {"role": "user", "content": text}], timeout=timeout), "total_cost_usd": 0}
        if agents.CLI != "claude":
            return agents.run_other(self.sistem + "\n\n" + text, C["agent"]["light_model"] or None, timeout)
        with self.lock:
            if self._alive() and self.turns >= self.TUR:
                self._kill()
            if not self._alive():
                self._start()
            return self._send(text, timeout)


class Tek:
    """Sürekli modu olmayan ajan CLI'leri (gemini, codex, opencode) için Beyin'in yerini tutar: her mesaj tek koşu.
    Süreklilik pentarch.py'nin mesaja eklediği konuşma arası satırlardan ve ilk mesajdaki çekirdek hafızadan gelir."""

    def __init__(self, model=None, effort=None, log=print, ilk=None):
        self.model, self.log, self.ilk = model, log, ilk
        self.gorulen, self.ofset, self.turns, self.ctx, self.summary = set(), 0, 0, 0, ""
        self.lock = threading.Lock()

    def ask(self, text, timeout=900, ek=None):
        with self.lock:
            if self.ilk:
                text = self.ilk() + "\n\n" + text
            if ek:
                text += ek(self.gorulen)
            out = agents.run_other(text, self.model, timeout)
            self.turns += 1
            return out

    def rotate(self, summarize=True):
        self.gorulen = set()

    def close(self):
        pass


def yeni(model, effort, log=print, ilk=None):
    """Ayarlı ajan CLI'sine göre sürekli (claude) ya da tek atımlık beyin."""
    return Beyin(model, effort, log=log, ilk=ilk) if agents.CLI == "claude" else Tek(model, effort, log=log, ilk=ilk)
