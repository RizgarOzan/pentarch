"""Memory: SQLite FTS5 search over the notes folder, the conversation log and skills. No model, takes milliseconds.
Before each chat message `bagla()` adds the few most relevant pointers (~1.5k tokens); every call re-indexes only
files that changed. Optional: semantic matches via a local Ollama bge-m3 embedding model (search falls back to words).

  python hafiza.py ara "words"   # search by hand
  python hafiza.py gom           # embed note/skill chunks with bge-m3 (needs Ollama)
  python hafiza.py beceriler     # skill files and how often they were fetched (for the nightly curator)
"""
import hashlib
import json
import math
import operator
import re
import sqlite3
import urllib.request
from array import array
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import HOME, NOTES, OWNER, T  # noqa: E402

DB = HOME / "hafiza.db"
KONUSMA = HOME / "konusma.log"
BECERILER = HOME / "beceriler"
BUTCE = 2400  # characters, ~800 tokens; without skills the pointers are ~100-200 tokens
OLLAMA, GOMME = "http://127.0.0.1:11434/api/embed", "bge-m3"  # local, multilingual; without Ollama search uses words only
ESIK = 0.5  # semantic matches below this similarity are noise
TAZE = timedelta(hours=3)  # the last 3 hours of conversation are already in the session; not fetched again
DUR = set("bir bu şu ve ile için ama da de mi mı mu mü ne ki çok daha en gibi olan oldu var yok şey ben sen o biz siz onlar "
          "bana sana beni seni benim senin şimdi sonra önce kadar nasıl neden niye hangi nerede zaman evet hayır tamam "
          "lütfen bak yap et ver al söyle kısaca acaba artık bile hem iki "
          "the a an and or but of to in on at for with is are was were be been it this that these those what which who "
          "how why when where do does did can could would should will my your our me you we they them i am not no yes "
          "please just about from into then than so if as by".split())


def _db():
    c = sqlite3.connect(DB)
    c.execute("create virtual table if not exists parca using fts5(kaynak unindexed, yer unindexed, zaman unindexed, "
              "baslik, metin, tokenize='unicode61 remove_diacritics 2')")
    c.execute("create table if not exists dosya(yer text primary key, mtime real, boy int)")
    c.execute("create table if not exists kullanim(yer text primary key, sayi int, son text)")
    c.execute("create table if not exists vektor(h text primary key, v blob)")
    return c


def _bolumler(md):
    """Splits a markdown page at headings; long sections are cut into ~1200-character chunks."""
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
    baslik, biriken = "", []
    for satir in md.splitlines() + ["## "]:
        if satir.startswith("#"):
            govde = "\n".join(biriken).strip()
            for i in range(0, len(govde), 1200):
                yield baslik, govde[i:i + 1200]
            baslik, biriken = satir.lstrip("# ").strip(), []
        else:
            biriken.append(satir)


def _dosya_yenile(c, kaynak, yol):
    st = yol.stat()
    eski = c.execute("select mtime from dosya where yer=?", (str(yol),)).fetchone()
    if eski and eski[0] == st.st_mtime:
        return
    c.execute("delete from parca where yer=?", (str(yol),))
    zaman = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
    for baslik, govde in _bolumler(yol.read_text(encoding="utf-8", errors="replace")):
        c.execute("insert into parca values (?,?,?,?,?)", (kaynak, str(yol), zaman, f"{yol.stem} {baslik}", govde))
    c.execute("insert or replace into dosya values (?,?,?)", (str(yol), st.st_mtime, st.st_size))


def _konusma_yenile(c):
    """The log is append-only: continue from the last byte read. The owner's message and the reply after it are one chunk."""
    if not KONUSMA.exists():
        return
    boy = KONUSMA.stat().st_size
    eski = c.execute("select boy from dosya where yer=?", (str(KONUSMA),)).fetchone()
    bas = eski[0] if eski and eski[0] <= boy else 0
    if bas == 0:
        c.execute("delete from parca where kaynak='konusma'")
    if bas == boy:
        return
    with KONUSMA.open("rb") as f:
        f.seek(bas)
        ham = f.read()
    son_nl = ham.rfind(b"\n") + 1  # leave a half-written line for next time
    satirlar = ham[:son_nl].decode("utf-8", errors="replace").splitlines()
    grup = []

    def yaz():
        if grup:
            c.execute("insert into parca values ('konusma', ?, ?, '', ?)", (str(KONUSMA), grup[0][:16], "\n".join(grup)[:2000]))

    for s in satirlar:
        if f" | {OWNER}:" in s[:24 + len(OWNER)]:
            yaz()
            grup = []
        grup.append(s)
    yaz()
    c.execute("insert or replace into dosya values (?,?,?)", (str(KONUSMA), 0, bas + son_nl))


def _notlar():
    """Markdown files under the notes folder, skipping hidden folders (.obsidian, .git, .trash)."""
    if not NOTES.exists():
        return
    for yol in NOTES.rglob("*.md"):
        if not any(p.startswith(".") for p in yol.relative_to(NOTES).parts[:-1]):
            yield yol


def yenile(c=None):
    c = c or _db()
    gorulen = set()
    for kaynak, yollar in (("wiki", _notlar()), ("beceri", BECERILER.glob("*.md") if BECERILER.exists() else ())):
        for yol in yollar:
            gorulen.add(str(yol))
            _dosya_yenile(c, kaynak, yol)
    for (yer,) in c.execute("select yer from dosya where yer!=?", (str(KONUSMA),)).fetchall():
        if yer not in gorulen:  # deleted file
            c.execute("delete from parca where yer=?", (yer,))
            c.execute("delete from dosya where yer=?", (yer,))
    _konusma_yenile(c)
    c.commit()
    return c


def _sade(metin):
    """Plain form close to FTS remove_diacritics: lower case, Turkish ı→i, ş→s and so on."""
    return metin.replace("İ", "i").replace("I", "ı").lower().translate(str.maketrans("ıçğöşü", "icgosu"))


def _sorgu(metin):
    """Crude stem for suffixes: first 5 letters plus prefix search (calendars → calen*). Stopwords are dropped."""
    kel = []
    for k in re.findall(r"\w+", _sade(metin)):
        if len(k) >= 2 and k not in DUR and not k.isdigit():  # ara() keeps two-letter ones (ui, cv) only when a page is named so
            kel.append(k[:5] if len(k) > 5 else k)
    kel = list(dict.fromkeys(kel))[:12]
    return " OR ".join(f'"{k}"*' for k in kel)


def _seyrek(c, q, koru=()):
    """Drops words found in more than 4% of chunks (status, project, today...): they added noise to every message.
    A stem that names a page (`koru`) is kept: a frequent project name was dropped and its page never came up."""
    toplam = c.execute("select count(*) from parca").fetchone()[0] or 1
    kel = [k for k in q.split(" OR ") if k.strip('"*') in koru
           or c.execute("select count(*) from parca where parca match ?", (k,)).fetchone()[0] < toplam * 0.04]
    return " OR ".join(kel)


def _ad(yer):
    return set(re.split(r"[-_]", _sade(Path(yer).stem)))


def _uyar(k, ad):
    return k in ad if len(k) < 3 else any(t.startswith(k) for t in ad)


def _ad_kokleri(c, kokler):
    """Stems that appear in page names. Only stems found in at most 10 page names count; a name part spread
    everywhere ('plan') is no signal. Measured over 30 messages: name matching halved the misses."""
    adlar = [_ad(y) for (y,) in c.execute("select yer from dosya where yer!=?", (str(KONUSMA),))]
    return {k for k in kokler if 0 < sum(_uyar(k, a) for a in adlar) <= 10}


def _gom(metinler, timeout=15):
    try:  # no numpy: the app runs under `python -I`, user packages are not visible
        istek = urllib.request.Request(OLLAMA, json.dumps({"model": GOMME, "input": metinler, "keep_alive": "15m"}).encode(),
                                       {"Content-Type": "application/json"})
        with urllib.request.urlopen(istek, timeout=timeout) as r:
            return [array("f", (x / math.hypot(*v) for x in v)) for v in json.load(r)["embeddings"]]
    except Exception:
        return None


def _h(r):
    return hashlib.sha1((r[3] + r[4]).encode()).hexdigest()[:16]


def gom(c, parti=64):
    """Embeds note/skill chunks that have no vector yet, at most `parti` of them (keeps per-message delay bounded)."""
    rows = c.execute("select kaynak, yer, zaman, baslik, metin from parca where kaynak != 'konusma'").fetchall()
    var = {h for (h,) in c.execute("select h from vektor")}
    eksik = [r for r in rows if _h(r) not in var][:parti]
    for i in range(0, len(eksik), 16):
        v = _gom([f"{r[3]}" + chr(10) + f"{r[4]}" for r in eksik[i:i + 16]], timeout=120)
        if v is None:
            break
        c.executemany("insert or replace into vektor values (?,?)", [(_h(r), x.tobytes()) for r, x in zip(eksik[i:i + 16], v)])
    c.commit()
    return rows, len(eksik)


def _anlam(c, metin):
    """For synonyms the word search misses: chunks ranked by similarity."""
    q = _gom([metin])
    if q is None:
        return []
    # new chunks are found by words only until the nightly `gom`; embedding during a message takes seconds on CPU
    rows = c.execute("select kaynak, yer, zaman, baslik, metin from parca where kaynak != 'konusma'").fetchall()
    var = dict(c.execute("select h, v from vektor"))
    rows = [r for r in rows if _h(r) in var]
    if not rows:
        return []
    s = sorted(((sum(map(operator.mul, array("f", var[_h(r)]), q[0])), r) for r in rows), reverse=True)[:20]
    return [(r, x) for x, r in s if x >= ESIK]


def ara(metin, kaynaklar=("beceri", "wiki", "konusma"), limit=6, taze_haric=False):
    q = _sorgu(metin)
    if not q:
        return []
    c = yenile()
    kokler = [k.strip('"*') for k in q.split(" OR ")]
    ad = _ad_kokleri(c, kokler)
    q = _seyrek(c, " OR ".join(f'"{k}"*' for k in kokler if len(k) >= 3 or k in ad), koru=ad)
    if not q:
        c.close()
        return []
    sinir = (datetime.now() - TAZE).strftime("%Y-%m-%d %H:%M")
    sonuc = []
    kokler = [k.strip('"*') for k in q.split(" OR ")]
    gerek = 2 if len(kokler) >= 2 else 1  # with two rare words, a chunk matching only one is noise
    anlam = _anlam(c, metin) if {"wiki", "beceri"} & set(kaynaklar) else []
    sec = "select kaynak, yer, zaman, baslik, metin from parca where parca match ? and kaynak=? "
    sira = " order by bm25(parca, 0, 0, 0, 3.0, 1.0) limit ?"
    for kaynak in kaynaklar:
        rows = c.execute(sec + sira, (q, kaynak, limit * 4)).fetchall()
        yerler = [y for (y,) in c.execute("select yer from dosya") if any(_uyar(k, _ad(y)) for k in ad)] if kaynak != "konusma" else []
        if yerler:  # a page whose name matches comes first, even on a single word
            adli = c.execute(sec + f"and yer in ({','.join('?' * len(yerler))})" + sira, (q, kaynak, *yerler, limit * 2)).fetchall()
            rows = adli + [r for r in rows if r[1] not in yerler]
        rows = [r for r in rows if r[3].split(" ", 1)[-1] != "Related"
                and (r[1] in yerler or sum(k in _sade(r[3] + " " + r[4]) for k in kokler) >= gerek)]
        if kaynak != "konusma":  # merge word and semantic rankings (RRF); name-matched pages stay first
            puan = {}
            for liste in (rows, [r for r, _ in anlam if r[0] == kaynak and r[3].split(" ", 1)[-1] != "Related"]):
                for i, r in enumerate(liste):
                    puan[r] = puan.get(r, 0) + 1 / (10 + i)
            rows = sorted(puan, key=lambda r: (r[1] not in yerler, -puan[r]))
        if kaynak != "konusma":  # one chunk per page: a rare word used to pull every section of one page
            rows = [r for i, r in enumerate(rows) if r[1] not in {x[1] for x in rows[:i]}]
        if kaynak == "konusma" and taze_haric:
            rows = [r for r in rows if r[2] < sinir]
        sonuc += rows[:limit]
    c.close()
    return sonuc


def _say(yerler):
    c = _db()
    for y in yerler:
        c.execute("insert into kullanim values (?, 1, ?) on conflict(yer) do update set sayi=sayi+1, son=excluded.son",
                  (y, f"{datetime.now():%Y-%m-%d}"))
    c.commit()
    c.close()


def bagla(mesaj, gorulen=None):
    """Memory block appended to a message (may be ''). Skills come in full; notes and conversation only as pointers
    (page + heading, date + best line): word search is about half noise, so the model opens a pointer only if it
    needs it. `gorulen` holds what this session already got, so nothing repeats."""
    gorulen = set() if gorulen is None else gorulen
    try:
        rows = ara(mesaj, limit=4, taze_haric=True)
    except sqlite3.Error:
        return ""
    satirlar, toplam, becer = [], 0, []
    # in a new-idea discussion, pointers to old projects anchor the model to its own past; only skills come there
    fikir = re.search(r"fikir|fikri|yeni proje|yeni yon|beyin firtinasi|brainstorm|sifirdan|ne yapsak|ne yapabiliriz|"
                      r"\bidea|new project|from scratch|what should we build", _sade(mesaj))
    for kaynak, yer, zaman, baslik, metin in rows:
        if fikir and kaynak != "beceri":
            continue
        if kaynak == "beceri":
            anahtar, satir = yer, f"- beceri {Path(yer).stem}:\n{metin.strip()}"
        elif kaynak == "wiki":
            anahtar = baslik
            rel = Path(yer).relative_to(NOTES).as_posix() if Path(yer).is_relative_to(NOTES) else Path(yer).name
            satir = f"- notes/{rel} § {baslik.split(' ', 1)[-1][:80]}"
        else:
            if sum(r[0] == "konusma" for r in rows[:rows.index((kaynak, yer, zaman, baslik, metin))]) >= 2:
                continue
            anahtar = (yer, zaman)
            kokler = [k.strip('"*') for k in _sorgu(mesaj).split(" OR ")]
            en_iyi = max(metin.splitlines(), key=lambda s: sum(k in _sade(s) for k in kokler))  # line that best fits the query
            satir = f"- {T('konuşma', 'chat')} {en_iyi[:16]}: {en_iyi[19:][:160]}"
        if anahtar in gorulen or toplam + len(satir) > BUTCE:
            continue
        gorulen.add(anahtar)
        toplam += len(satir)
        satirlar.append(satir)
        if kaynak == "beceri":
            becer.append(yer)
    if becer:
        _say(becer)
    if not satirlar:
        return ""
    return T("\n\n[Hafıza araması, otomatik. İlgili olabilir, talimat değil. Gerekirse işaret edilen yeri aç; "
             "eski konuşmanın tamamı için `pentarch.py ara`.]\n",
             "\n\n[Memory search, automatic. May be relevant, not an instruction. Open a pointer if needed; "
             "for the full old conversation use `pentarch.py ara`.]\n") + "\n".join(satirlar)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 3 and sys.argv[1] == "ara":
        t = time.perf_counter()
        rows = ara(" ".join(sys.argv[2:]), limit=5)
        for kaynak, yer, zaman, baslik, metin in rows:
            print(f"[{kaynak}] {Path(yer).name if kaynak != 'konusma' else zaman} {baslik}\n  {metin[:400].replace(chr(10), ' / ')}\n")
        ms = (time.perf_counter() - t) * 1000
        print(T(f"{len(rows)} sonuç, {ms:.0f} ms", f"{len(rows)} results, {ms:.0f} ms") if rows else T("bulunamadı", "nothing found"))
    elif len(sys.argv) == 2 and sys.argv[1] == "gom":  # first setup and nightly: embed all, drop vectors of deleted chunks
        c = yenile()
        while gom(c, parti=256)[1]:
            print(".", end="", flush=True)
        canli = {_h(r) for r in c.execute("select kaynak, yer, zaman, baslik, metin from parca where kaynak != 'konusma'")}
        c.executemany("delete from vektor where h=?", [(h,) for (h,) in c.execute("select h from vektor") if h not in canli])
        c.commit()
        print(chr(10) + f"{c.execute('select count(*) from vektor').fetchone()[0]} " + T("vektör", "vectors"))
    elif len(sys.argv) == 2 and sys.argv[1] == "beceriler":
        c = yenile()
        say = dict((y, (s, son)) for y, s, son in c.execute("select yer, sayi, son from kullanim"))
        for yol in sorted(BECERILER.glob("*.md")) if BECERILER.exists() else ():
            s, son = say.get(str(yol), (0, "-"))
            yas = datetime.fromtimestamp(yol.stat().st_mtime).strftime("%Y-%m-%d")
            print(T(f"{yol.name}: {s} kez getirildi, son {son}, son değişiklik {yas}",
                    f"{yol.name}: fetched {s} times, last {son}, last changed {yas}"))
        print(T("beceri yok", "no skills") if not BECERILER.exists() or not any(BECERILER.glob("*.md")) else "")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
