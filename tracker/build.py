# -*- coding: utf-8 -*-
"""Tracker: a small, LLM-free dashboard builder (a Pentarch module).

Reads JSON files from a data folder and writes two views of the same content:
  index.html  desktop dashboard, works offline (no CDN, no web fonts)
  README.md   plain Markdown for phones or the GitHub app

The "brain" is rule-based. It picks today's one task from the weekly rhythm and close deadlines, and writes
notes about passed deadlines, records nobody checked for a while, learning weeks that ended but were never
marked done, and the open-source pace needed to reach a goal.

Usage: python build.py [--config config.json] [--data DIR] [--out DIR] [--lang en|tr] [--today YYYY-MM-DD]
Python 3.10+, standard library only.
"""
import argparse, datetime, html, json, pathlib, re, shutil, subprocess

HERE = pathlib.Path(__file__).parent
DEFAULTS = {"title": "", "lang": "en", "data_dir": "data", "out_dir": "out", "backlog": "", "status_log": "",
            "github_user": "", "important_repos": [], "oss_goal": 0, "oss_deadline": "", "stale_days": 10, "new_days": 8, "followup_days": 14}
PATH_KEYS = ("data_dir", "out_dir", "backlog", "status_log")
STAGES = ("ready", "sent", "process", "decide", "watching", "closed")

STR = {
    "en": dict(
        title="Tracker",
        sample="Sample data from example-data/. Edit the files in data/ (or let the assistant do it) and delete data/SAMPLE to hide this.",
        months=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        months_long=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
        days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        days_short=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        ago="{n} days ago", today="today", tomorrow="tomorrow", yesterday="yesterday", in_days="{n} days",
        t_app="Application", t_event="Event", t_task="To do", t_learn="Learning",
        week="Week {w}", starts=" — starts",
        plan_starts="Plan starts {d}; starting early is fine. ", plan_done="Plan finished", add_course="Add a new course to learning.json.",
        rest="Rest day", rest_alt="Nothing scheduled today.", learning="learning", rest_short="rest",
        n_deadline="{c}: deadline passed {n} days ago; update the status if you applied, otherwise close it.",
        n_stale="Not checked for {n}+ days: {xs}.",
        n_overdue="Overdue task ({n} days): {x}",
        n_followup="Sent {n}+ days ago, no answer yet: {xs}. Send a short follow-up or move it to closed.",
        top_new="best",
        n_done="Finished? {xs}. If so, mark it done; if not, shift the dates.",
        n_gh="Could not get PR counts from gh.",
        n_oss="Open source: {r:.1f} merges a day needed to reach {g} ({n} days left).",
        nav_today="Today", nav_apps="Applications", nav_scan="Scan", nav_learn="Learning", nav_oss="Open source", nav_other="Other",
        sections="Sections", last_build="Last build",
        one_task="Today's one task", start="Start", first="First this:", notes="Notes", next14="Next 14 days", passed="passed",
        waiting="Waiting on you", nothing_waiting="Nothing is waiting on you right now.", open_board="Open board",
        c_sent="sent", c_ready="ready", c_decide="to decide",
        last_sent="Last sent: {c}, {d}. ", oldest="Oldest awaiting reply: {c}, {n} days.",
        upcoming="Upcoming", days14="14 days", nothing14="Nothing is due in the next 14 days.",
        scan="Job scan", c_new="new", c_changed="changed", c_closed="closed",
        scan_stale="The scan is more than a week old; the scan job may not have run.", details="Details",
        no_scan="No scan yet. It shows up here after the first run.",
        new_badge="new", deadline="Deadline", check_stale=" · check is stale", last_check="Last checked {d}",
        l_package="Package", l_cv="CV", l_posting="Posting",
        st_ready="Ready", st_sent="Sent", st_process="In process", st_decide="Decide", st_watching="Watching", st_closed="Closed",
        sd_ready="package ready, to send", sd_sent="waiting for a reply", sd_process="assessment, interview, offer",
        sd_decide="requirements unclear", sd_watching="waiting for a posting or a package",
        pipeline="Application pipeline", open_closed="{a} open · {c} closed", search="Search", search_ph="Search company, role, city",
        closed_apps="Closed applications ({n})", none="Nothing here.",
        new_postings="New postings", changed="Changed", closed="Closed", dropped="Looked at and dropped ({n})", sources="Sources checked: ",
        plan="Learning plan", to_start="{n} days to start", to_end="{n} days left", when_done="When done:",
        s_done=" · done", s_now=" · now", s_next=" · next", rhythm="Weekly rhythm", later="Later / spare time ({n})",
        oss="Open source", pr_list="PR list", goal_line="/ {g} merged · goal {d}", merged="merged",
        oss_sub="key repos {i} · open PRs {o}", next_x="Next: {x}",
        events="Events", no_events="No upcoming events.", past_events="Past / closed ({n})", reg_by="registration {d}", note="Note",
        certs="Certifications", target="target {d}", jobs="Background jobs",
        md_task="Today's task ({tip}):", md_upcoming="Upcoming (14 days)", md_open="open", md_passed="passed",
        md_apps_head="| Company | Role | Deadline | Status | Links |", md_scan="Job scan ({d})",
        md_new="New", md_changed="Changed", md_closed="Closed", md_rhythm="Rhythm: ",
        md_learn_head="| Week | Course | Dates | Status |", md_due="due", md_projects="Projects", md_next="next",
        md_oss="**Open source** merged {m}{g} (key repos {i}), open {o}", md_reg="registration",
        md_cert_head="| # | Name | Cost · time | Target | Status |",
    ),
    "tr": dict(
        title="Takip",
        sample="Bu örnek veri (example-data/). data/ içindeki dosyaları düzenle (ya da asistana bırak) ve bu yazıyı kaldırmak için data/SAMPLE dosyasını sil.",
        months=["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"],
        months_long=["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
        days=["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"],
        days_short=["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"],
        ago="{n} gün geçti", today="bugün", tomorrow="yarın", yesterday="dün", in_days="{n} gün",
        t_app="Başvuru", t_event="Etkinlik", t_task="Senden", t_learn="Eğitim",
        week="Hafta {w}", starts=" — başlıyor",
        plan_starts="Plan {d} başlıyor; erken başlamak serbest. ", plan_done="Plan bitti", add_course="learning.json'a yeni eğitim ekle.",
        rest="Boş gün", rest_alt="Bugün planlı bir şey yok.", learning="eğitim", rest_short="boş",
        n_deadline="{c}: son tarih {n} gün önce geçti; başvurulduysa durumu güncelle, değilse kapat.",
        n_stale="{n}+ gündür kontrol edilmeyen ilan: {xs}.",
        n_overdue="Gecikmiş iş ({n} gün): {x}",
        n_followup="{n}+ gün önce gönderildi, cevap yok: {xs}. Kısa bir hatırlatma yaz ya da kapat.",
        top_new="en iyi",
        n_done="Bitti mi? {xs}. Bittiyse işaretle; bitmediyse tarihleri kaydır.",
        n_gh="gh'den PR sayısı alınamadı.",
        n_oss="Açık kaynak: {g} merge için günde {r:.1f} merge gerekiyor ({n} gün kaldı).",
        nav_today="Bugün", nav_apps="Başvurular", nav_scan="Tarama", nav_learn="Eğitim", nav_oss="Açık kaynak", nav_other="Diğer",
        sections="Bölümler", last_build="Son derleme",
        one_task="Bugünün tek işi", start="Başla", first="Önce bu:", notes="Notlar", next14="Önümüzdeki 14 gün", passed="geçti",
        waiting="Senden beklenen", nothing_waiting="Şu an senden beklenen bir şey yok.", open_board="Panoyu aç",
        c_sent="gönderildi", c_ready="hazır", c_decide="karar bekliyor",
        last_sent="Son giden: {c}, {d}. ", oldest="Cevap bekleyen en eski: {c}, {n} gün.",
        upcoming="Yaklaşan", days14="14 gün", nothing14="14 gün içinde kapanan bir şey yok.",
        scan="İlan taraması", c_new="yeni ilan", c_changed="değişen", c_closed="kapanan",
        scan_stale="Tarama bir haftadan eski; tarama görevi çalışmamış olabilir.", details="Ayrıntılar",
        no_scan="Henüz tarama yok. Tarama görevi ilk kez çalışınca burada görünür.",
        new_badge="yeni", deadline="Son başvuru", check_stale=" · kontrol eski", last_check="Son kontrol {d}",
        l_package="Paket", l_cv="CV", l_posting="İlan",
        st_ready="Hazır", st_sent="Gönderildi", st_process="Süreçte", st_decide="Karar ver", st_watching="İzleniyor", st_closed="Kapalı",
        sd_ready="paket hazır, gönderilecek", sd_sent="cevap bekleniyor", sd_process="test, mülakat, teklif",
        sd_decide="şartlar belirsiz", sd_watching="ilan ya da paket bekleniyor",
        pipeline="Başvuru hattı", open_closed="{a} açık · {c} kapalı", search="Ara", search_ph="Şirket, rol, şehir ara",
        closed_apps="Kapalı başvurular ({n})", none="Yok.",
        new_postings="Yeni ilan", changed="Değişen", closed="Kapanan", dropped="Bakılıp elenen ilanlar ({n})", sources="Bakılan yerler: ",
        plan="Eğitim planı", to_start="başlamasına {n} gün", to_end="bitişe {n} gün", when_done="Bitince:",
        s_done=" · bitti", s_now=" · şimdi", s_next=" · sıradaki", rhythm="Haftalık ritim", later="Sonra / boş vakit ({n})",
        oss="Açık kaynak", pr_list="PR listesi", goal_line="/ {g} merge · hedef {d}", merged="merge",
        oss_sub="önemli repolar {i} · açık PR {o}", next_x="Sıradaki: {x}",
        events="Etkinlikler", no_events="Açık etkinlik yok.", past_events="Geçmiş / kapalı ({n})", reg_by="kayıt {d}", note="Not",
        certs="Sertifikalar", target="hedef {d}", jobs="Arkada çalışanlar",
        md_task="Bugünün işi ({tip}):", md_upcoming="Yaklaşanlar (14 gün)", md_open="aç", md_passed="geçti",
        md_apps_head="| Şirket | Rol | Son tarih | Durum | Linkler |", md_scan="İlan taraması ({d})",
        md_new="Yeni", md_changed="Değişti", md_closed="Kapandı", md_rhythm="Ritim: ",
        md_learn_head="| Hafta | Eğitim | Tarih | Durum |", md_due="son", md_projects="Projeler", md_next="sıradaki",
        md_oss="**Açık kaynak** merge {m}{g} (önemli repolar {i}), açık {o}", md_reg="kayıt",
        md_cert_head="| # | Ad | Ücret · süre | Hedef | Durum |",
    ),
}

# Field defaults per file: every record gets these keys, so the data files only need what they use.
FIELDS = {
    "applications.json": dict(id="", company="", role="", location="", deadline="", deadline_note="", stage="watching", status="",
                              sent_on="", cv="", package="", posting="", priority=2, note="", checked="", added=""),
    "learning.json": dict(id="", order=0, priority="", week="", start="", end="", name="", provider="", link="", scope="", done_when="", status=""),
    "events.json": dict(id="", name="", date="", date_end="", register_by="", status="", closed=False, link="", note=""),
    "certifications.json": dict(id="", order=0, name="", provider="", cost="", duration="", target="", status="", link=""),
    "tasks.json": dict(id="", task="", effort="", link="", due="", done=False),
}

# Set by build(); the helpers below read them.
TODAY, CFG, S, DATA, OUT = datetime.date.today(), dict(DEFAULTS), STR["en"], HERE / "data", HERE / "out"

def J(name, default=None):
    p = DATA / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        sys.exit(f"{p}: not valid JSON ({e})")
def rows(name):
    base = FIELDS[name]
    fix = lambda k, v: str(v) if isinstance(base.get(k), str) and not isinstance(v, str) else v
    return [{**base, **{k: fix(k, v) for k, v in r.items() if v is not None}} for r in (J(name) or []) if isinstance(r, dict)]
def d(s):
    try: return datetime.date.fromisoformat(s) if s else None
    except Exception: return None
def days(s):
    x = d(s); return (x - TODAY).days if x else None
def esc(s): return html.escape(str(s or ""))
def kisa_tarih(s): x = d(s); return f"{x.day} {S['months'][x.month - 1]}" if x else "—"
def long_date(x): return f"{x.day} {S['months_long'][x.month - 1]} {S['days'][x.weekday()]}"
def stage(b): return b["stage"] if b["stage"] in STAGES else "watching"
def short(s): return re.split(r"[:(]", s)[0].strip()

def load_config(path=None, **over):
    """Config file values, then CLI overrides. Paths in the file are relative to the file; CLI paths to the cwd."""
    cfg, base = dict(DEFAULTS), HERE
    if path:
        path = pathlib.Path(path)
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
        base = path.resolve().parent
    for k in PATH_KEYS:
        if cfg[k]: cfg[k] = (base / cfg[k]).resolve()
    for k, v in over.items():
        if v: cfg[k] = pathlib.Path(v).resolve() if k in PATH_KEYS else v
    return cfg

def gh_counts(user, important):
    """Merged / open PR counts on other people's repos. Skipped (all None) without a user name or the gh CLI."""
    out = {"merged": None, "open": None, "important": None}
    if not user or not shutil.which("gh"): return out
    try:
        def q(extra):
            r = subprocess.run(["gh", "search", "prs", "--author", user, "--limit", "200", "--json", "repository",
                                "--jq", ".[].repository.nameWithOwner"] + extra, capture_output=True, text=True, timeout=60, check=True)
            return [l for l in r.stdout.split() if l and not l.lower().startswith(user.lower() + "/")]
        m = q(["--merged"]); o = q(["--state", "open"])
        out.update(merged=len(m), open=len(o), important=sum(1 for r in m if r in set(important)))
    except Exception: pass
    return out

def backlog_progress(path):
    """Counts `- [x]` / `- [ ]` under each `## ` heading of a Markdown file; headings without checkboxes are skipped."""
    if not path or not pathlib.Path(path).exists(): return []
    rows_ = []
    for s in re.split(r"^## ", pathlib.Path(path).read_text(encoding="utf-8"), flags=re.M)[1:]:
        done = len(re.findall(r"^- \[x\]", s, flags=re.M | re.I)); todo = len(re.findall(r"^- \[ \]", s, flags=re.M))
        if not done + todo: continue
        nxt = re.search(r"^- \[ \] (.+)", s, flags=re.M)
        rows_.append(dict(title=s.splitlines()[0].strip().split(" — ")[0], done=done, total=done + todo, next=(nxt.group(1)[:110] if nxt else "—")))
    return rows_

def status_lines(path):
    p = pathlib.Path(path) if path else None
    return [l.strip() for l in p.read_text(encoding="utf-8-sig").splitlines()[-8:]] if p and p.exists() else []

def build(cfg=None, today=None):
    global TODAY, CFG, S, DATA, OUT
    CFG = cfg or load_config()
    TODAY = today or datetime.date.today()
    S = STR.get(CFG["lang"], STR["en"])
    DATA, OUT = pathlib.Path(CFG["data_dir"]), pathlib.Path(CFG["out_dir"])
    OUT.mkdir(parents=True, exist_ok=True)

    bas = sorted(rows("applications.json"), key=lambda x: (x["priority"], x["deadline"] or "9"))
    ser = sorted(rows("certifications.json"), key=lambda x: x["order"])
    egt = sorted(rows("learning.json"), key=lambda x: x["order"])
    etk = sorted(rows("events.json"), key=lambda x: x["date"])
    rit = {"session": "", "note": "", "days": ["rest"] * 7, "practices": {}, **(J("rhythm.json") or {})}
    man = sorted([m for m in rows("tasks.json") if not m["done"]], key=lambda x: days(x["due"]) if x["due"] else 9999)
    tarama = J("scan.json")
    gh = gh_counts(CFG["github_user"], CFG["important_repos"]); prog = backlog_progress(CFG["backlog"]); rut = status_lines(CFG["status_log"])
    acik = sorted([b for b in bas if stage(b) != "closed"], key=lambda b: (days(b["deadline"]) if b["deadline"] else 9999, b["priority"]))
    kapali = [b for b in bas if stage(b) == "closed"]
    plan = [g for g in egt if g["start"]]; sonra = [g for g in egt if not g["start"]]
    cur = next((g for g in plan if g["status"] != "done" and (days(g["end"]) or 0) >= 0), None)

    # Upcoming: applications / events / tasks closing within 14 days, plus this week's learning
    bugun = []
    for b in acik:
        k = days(b["deadline"])
        if k is not None and -3 <= k <= 14: bugun.append(("app", f'{b["company"]} — {b["role"]}', k, b["posting"]))
    for e in etk:
        k = days(e["register_by"] or e["date"])
        if k is not None and 0 <= k <= 14 and not e["closed"]: bugun.append(("event", e["name"], k, e["link"]))
    for m in man:
        k = days(m["due"])
        if k is not None and -3 <= k <= 14: bugun.append(("task", m["task"], k, m["link"]))
    for g in egt:
        b, k = days(g["start"]), days(g["end"])
        if b is not None and b <= 7 and k is not None and k >= 0 and g["status"] != "done":
            bugun.append(("learn", S["week"].format(w=g["week"]) + f': {g["name"]}' + ("" if b <= 0 else S["starts"]), k if b <= 0 else b, g["link"]))
    # When a task and an event share a link, only the task stays
    gorulen = {u for t, n, k, u in bugun if t == "task" and u}
    bugun = [x for x in bugun if not (x[0] == "event" and x[3] in gorulen)]
    bugun.sort(key=lambda x: x[2])

    # Today's one task: something closing within 3 days comes first, then the rhythm
    acil = [x for x in bugun if x[0] in ("app", "task") and x[2] <= 3]  # older delays go to the notes
    gun_tipi = (rit["days"] + ["rest"] * 7)[TODAY.weekday()]
    pr = rit["practices"].get(gun_tipi)
    if gun_tipi == "learning" and cur:
        b0 = days(cur["start"])
        odak = dict(baslik=cur["name"], alt=(S["plan_starts"].format(d=kisa_tarih(cur["start"])) if b0 > 0 else "") + cur["scope"], link=cur["link"], tip=S["t_learn"])
    elif gun_tipi == "learning":
        g = sonra[0] if sonra else None
        odak = dict(baslik=g["name"] if g else S["plan_done"], alt=g["scope"] if g else S["add_course"], link=g["link"] if g else "", tip=S["t_learn"])
    elif pr:
        odak = dict(baslik=pr.get("name", gun_tipi), alt=pr.get("goal", ""), link=pr.get("link", ""), tip=pr.get("label", gun_tipi))
    else:
        odak = dict(baslik=S["rest"], alt=S["rest_alt"], link="", tip=S["rest"])

    # Notes: warnings that come from the data itself
    notlar, bayat, gecen = [], [], []
    for b in acik:
        k, kt = days(b["deadline"]), days(b["checked"])
        if k is not None and k < -3: notlar.append(S["n_deadline"].format(c=b["company"], n=-k))
        elif kt is not None and -kt > CFG["stale_days"]: bayat.append(b["company"])
    if bayat: notlar.append(S["n_stale"].format(n=CFG["stale_days"], xs=", ".join(dict.fromkeys(bayat))))
    sessiz = [b["company"] for b in acik if stage(b) == "sent" and days(b["sent_on"]) is not None and -days(b["sent_on"]) >= CFG["followup_days"]]
    if sessiz: notlar.append(S["n_followup"].format(n=CFG["followup_days"], xs=", ".join(dict.fromkeys(sessiz))))
    for m in man:
        k = days(m["due"])
        if k is not None and k < -3: notlar.append(S["n_overdue"].format(n=-k, x=m["task"]))
    for g in plan:
        if g["status"] != "done" and (days(g["end"]) or 0) < 0: gecen.append(S["week"].format(w=g["week"]) + " " + g["name"].split(" (")[0])
    if gecen: notlar.append(S["n_done"].format(xs="; ".join(gecen)))
    mg, goal, left = gh["merged"], CFG["oss_goal"], days(CFG["oss_deadline"])
    if CFG["github_user"] and mg is None: notlar.append(S["n_gh"])
    elif mg is not None and goal and mg < goal and (left or 0) > 0:
        notlar.append(S["n_oss"].format(g=goal, r=(goal - mg) / left, n=left))

    ctx = dict(bas=bas, acik=acik, kapali=kapali, ser=ser, egt=egt, plan=plan, sonra=sonra, cur=cur, etk=etk, man=man, rit=rit, gh=gh,
               prog=prog, rut=rut, bugun=bugun, acil=acil, odak=odak, notlar=notlar, tarama=tarama)
    (OUT / "index.html").write_text(render_html(**ctx), encoding="utf-8")
    (OUT / "README.md").write_text(render_md(**ctx), encoding="utf-8")
    print("built", TODAY, "->", OUT, "| upcoming:", len(bugun), "notes:", len(notlar), "gh:", gh)
    return ctx

def badge(x):
    """Score pill for a scan item that has one (scan.py writes 1-5); nothing for hand-written items."""
    return f' <span class="pill s{int(x["score"])}">{int(x["score"])}/5</span>' if isinstance(x.get("score"), (int, float)) else ""
def type_label(t): return S[{"app": "t_app", "event": "t_event", "task": "t_task", "learn": "t_learn"}[t]]
def kalan(k):
    if k is None: return ""
    return S["ago"].format(n=-k) if k < 0 else S["today"] if k == 0 else S["tomorrow"] if k == 1 else S["in_days"].format(n=k)
def day_label(t, rit):
    return S["learning"] if t == "learning" else rit["practices"][t].get("label", t) if t in rit["practices"] else S["rest_short"]
def pr_url(): return f'https://github.com/pulls?q=is%3Apr+author%3A{CFG["github_user"]}+is%3Amerged'

def render_html(bas, acik, kapali, ser, egt, plan, sonra, cur, etk, man, rit, gh, prog, rut, bugun, acil, odak, notlar, tarama):
    def link(u, t, cls=""):
        c = f' class="{cls}"' if cls else ""
        return f'<a{c} href="{esc(u)}" target="_blank" rel="noopener">{t}</a>' if u else ""
    def flink(p, t):  # URL, or a file next to index.html (shown only if it exists)
        if p and re.match(r"https?://", p): return link(p, t)
        return f'<a href="{esc(p)}">{t}</a>' if p and (OUT / p).exists() else ""
    def urg(k): return "" if k is None else "past" if k < 0 else "hot" if k <= 7 else "warm" if k <= 21 else ""
    def links(*xs):
        xs = [x for x in xs if x]
        return '<span class="links">' + "".join(xs) + "</span>" if xs else ""
    panels = []

    # Today: one task, 14-day strip, three cards
    p = [f'<section class="panel" id="today" aria-label="{esc(S["nav_today"])}"><div class="hero"><div class="hero-is">'
         f'<div class="label">{esc(S["one_task"])} · {esc(odak["tip"])}</div><h2>{esc(odak["baslik"])}</h2><p>{esc(odak["alt"])}</p></div>'
         f'<div class="hero-go"><span class="mono">{esc(rit["session"])}</span>{link(odak["link"], esc(S["start"]), "go")}</div></div>']
    if acil:
        p.append(f'<p class="acil"><b>{esc(S["first"])}</b> ' + " · ".join(f'{link(u, esc(n)) or esc(n)} <span class="mono">{kalan(k)}</span>' for t, n, k, u in acil) + "</p>")
    if notlar:
        p.append(f'<ul class="notes" aria-label="{esc(S["notes"])}">' + "".join(f"<li>{esc(n)}</li>" for n in notlar) + "</ul>")

    gunler = {}
    for t, n, k, u in bugun: gunler.setdefault(max(k, 0), []).append((t, n, k, u))
    p.append(f'<div class="strip-wrap" id="upcoming"><ol class="strip" aria-label="{esc(S["next14"])}">')
    gecti = f'<small>{esc(S["passed"])}</small>'
    for i in range(14):
        x = TODAY + datetime.timedelta(days=i)
        isler = "".join(f'<li class="ev{" sert" if t in ("app", "task") else ""}{" past" if k < 0 else ""}" title="{esc(type_label(t))}: {esc(n)}">'
                        f'{link(u, esc(n)) or esc(n)}{gecti if k < 0 else ""}</li>' for t, n, k, u in gunler.get(i, []))
        p.append(f'<li class="gun{" today" if i == 0 else ""}{" hs" if x.weekday() >= 5 else ""}"><span class="g-ad">{S["days_short"][x.weekday()]}</span>'
                 f'<span class="g-no mono">{x.day}</span>' + (f'<ul>{isler}</ul>' if isler else "") + "</li>")
    p.append("</ol></div>")

    senden = ('<ul class="todo">' + "".join(
        f'<li class="{urg(days(mm["due"]))}"><div><span>{esc(mm["task"])}</span>'
        f'<small>{esc(mm["effort"])}{" · " + link(mm["link"], "↗") if mm["link"] else ""}</small></div><span class="mono due-s">{kalan(days(mm["due"])) or "—"}</span></li>'
        for mm in man) + "</ul>") if man else f'<p class="empty">{esc(S["nothing_waiting"])}</p>'
    sayac = {a: [b for b in acik if stage(b) == a] for a in STAGES[:-1]}
    giden = sorted([b for b in sayac["sent"] + sayac["process"] if d(b["sent_on"])], key=lambda b: b["sent_on"])
    son_giden = esc(S["last_sent"].format(c=giden[-1]["company"], d=kisa_tarih(giden[-1]["sent_on"]))) if giden else ""
    en_eski = esc(S["oldest"].format(c=giden[0]["company"], n=max(0, -days(giden[0]["sent_on"])))) if giden else ""
    kartlar = [
        f'<section class="card"><h3>{esc(S["waiting"])} <span class="mono">{len(man)}</span></h3>{senden}</section>',
        f'<section class="card"><h3>{esc(S["nav_apps"])} <a href="#applications">{esc(S["open_board"])}</a></h3><div class="nums">'
        + "".join(f'<div><b class="mono">{n}</b><span>{esc(t)}</span></div>' for n, t in
                  [(len(sayac["sent"]) + len(sayac["process"]), S["c_sent"]), (len(sayac["ready"]), S["c_ready"]), (len(sayac["decide"]), S["c_decide"])])
        + f'</div><p class="soft">{son_giden}{en_eski}</p></section>',
        f'<section class="card"><h3>{esc(S["upcoming"])} <span class="mono">{esc(S["days14"])}</span></h3>'
        + ('<ol class="agenda">' + "".join(f'<li class="{urg(k)}"><span><span class="type">{esc(type_label(t))}</span>{link(u, esc(n)) or esc(n)}</span><span class="mono">{kalan(k)}</span></li>'
                                            for t, n, k, u in bugun) + "</ol>" if bugun else f'<p class="empty">{esc(S["nothing14"])}</p>') + "</section>"]
    p.append('<div class="cards">' + "".join(kartlar) + "</div>")

    if tarama:
        tk = days(tarama.get("date"))
        yas = S["today"] if tk == 0 else S["yesterday"] if tk == -1 else S["ago"].format(n=-tk) if tk is not None else ""
        eski = tk is not None and -tk > 8
        ust = max(tarama.get("new", []), key=lambda x: x.get("score") or 0, default=None)
        sayi = [(len(tarama.get("new", [])), S["c_new"]), (len(tarama.get("changed", [])), S["c_changed"]), (len(tarama.get("closed", [])), S["c_closed"])]
        p.append(f'<div class="scan{" stale" if eski else ""}"><b>{esc(S["scan"])}</b><span class="soft">{esc(kisa_tarih(tarama.get("date")))} · {esc(yas)}</span>'
                 + "".join(f'<span><b class="mono">{n}</b> {esc(t)}</span>' for n, t in sayi)
                 + (f'<span class="warnline">{esc(S["scan_stale"])}</span>' if eski else "")
                 + (f'<span>{esc(S["top_new"])}: {link(ust.get("link"), esc(ust.get("company"))) or esc(ust.get("company"))} · {esc(ust.get("role"))}{badge(ust)}</span>' if ust else "")
                 + f'<a href="#scan">{esc(S["details"])}</a></div>')
    else:
        p.append(f'<div class="scan stale"><b>{esc(S["scan"])}</b><span class="soft">{esc(S["no_scan"])}</span></div>')
    p.append("</section>")
    panels.append("".join(p))

    # Applications: board with one column per stage
    def kart(b):
        kd = stage(b)
        kt = days(b["checked"])
        bayat = kt is not None and -kt > CFG["stale_days"]
        ek = days(b["added"])
        yeni = ek is not None and -ek < CFG["new_days"]
        extra = " · ".join(x for x in [b["deadline_note"], b["note"]] if x)
        yer = b["location"] if b["location"].strip("—- ") else ""
        g = b["sent_on"] if kd in ("sent", "process") and d(b["sent_on"]) else ""
        k = days(b["deadline"])
        sag = (f'<span class="mono chip">{esc(kisa_tarih(g))}</span>' if g else
               f'<span class="mono chip {urg(k)}" title="{esc(S["deadline"])}">{esc(kisa_tarih(b["deadline"]))} · {kalan(k)}</span>' if b["deadline"] and kd != "closed" else "")
        ara = " ".join([b["company"], b["role"], yer, b["status"]]).lower()
        return (f'<details class="kart {kd}" data-ara="{esc(ara)}"><summary><span class="k-ust"><b>{esc(b["company"])}</b>'
                + (f'<em class="new">{esc(S["new_badge"])}</em>' if yeni else "") + f'{sag}</span>'
                f'<span class="k-rol">{esc(b["role"])}{" · " + esc(yer) if yer else ""}</span>'
                f'<span class="k-st">{esc(short(b["status"]) or S["st_" + kd])}{esc(S["check_stale"]) if bayat else ""}</span></summary>'
                f'<div class="detail">' + (f'<p>{esc(b["status"])}</p>' if b["status"] else "") + (f'<p>{esc(extra)}</p>' if extra else "")
                + (f'<p class="kontrol">{esc(S["last_check"].format(d=kisa_tarih(b["checked"])))}</p>' if b["checked"] else "")
                + f'{links(flink(b["package"], esc(S["l_package"])), flink(b["cv"], esc(S["l_cv"])), link(b["posting"], esc(S["l_posting"])))}</div></details>')
    sayac["sent"].sort(key=lambda b: b["sent_on"], reverse=True)
    p = [f'<section class="panel" id="applications" aria-label="{esc(S["nav_apps"])}"><div class="p-head"><h2>{esc(S["pipeline"])}</h2>'
         f'<span class="soft">{esc(S["open_closed"].format(a=len(acik), c=len(kapali)))}</span>'
         f'<label class="ara"><span class="sr">{esc(S["search"])}</span><input type="search" id="search" placeholder="{esc(S["search_ph"])}" autocomplete="off"></label></div><div class="board">']
    for a in STAGES[:-1]:
        rs = sayac[a]
        if not rs and a not in ("ready", "sent", "process"): continue
        p.append(f'<section class="col {a}"><h3>{esc(S["st_" + a])} <span class="mono">{len(rs)}</span></h3><p class="col-alt">{esc(S["sd_" + a])}</p>'
                 + ("".join(kart(b) for b in rs) if rs else f'<p class="empty">{esc(S["none"])}</p>') + "</section>")
    p.append("</div>")
    if kapali:
        p.append(f'<details class="fold"><summary>{esc(S["closed_apps"].format(n=len(kapali)))}</summary><div class="closed-grid">' + "".join(kart(b) for b in kapali) + "</div></details>")
    p.append("</section>")
    panels.append("".join(p))

    # Scan details
    if tarama:
        def tcol(baslik, xs, f):
            return (f'<div class="card tcol"><h3>{esc(baslik)} <span class="mono">{len(xs)}</span></h3>'
                    + ('<ul>' + "".join(f(x) for x in xs) + "</ul>" if xs else f'<p class="empty">{esc(S["none"])}</p>') + "</div>")
        p = [f'<section class="panel" id="scan" aria-label="{esc(S["scan"])}"><div class="p-head"><h2>{esc(S["scan"])}</h2><span class="soft">{esc(kisa_tarih(tarama.get("date")))}</span></div>'
             + (f'<p class="lead">{esc(tarama["summary"])}</p>' if tarama.get("summary") else "") + '<div class="cards">'
             + tcol(S["new_postings"], tarama.get("new", []), lambda x: f'<li><b>{link(x.get("link"), esc(x.get("company"))) or esc(x.get("company"))}</b> {esc(x.get("role"))}{badge(x)}<small>{esc(" · ".join(filter(None, (x.get("location"), x.get("reason")))))}</small></li>')
             + tcol(S["changed"], tarama.get("changed", []), lambda x: f'<li><b>{esc(x.get("company"))}</b><small>{esc(x.get("what"))}</small></li>')
             + tcol(S["closed"], tarama.get("closed", []), lambda x: f'<li><b>{esc(x.get("company"))}</b><small>{esc(x.get("reason"))}</small></li>')
             + "</div>"]
        if tarama.get("dropped"):
            p.append(f'<details class="fold"><summary>{esc(S["dropped"].format(n=len(tarama["dropped"])))}</summary><ul class="plain">' + "".join(
                f'<li><b>{esc(x.get("company"))}</b> {esc(x.get("role"))}<small>{esc(x.get("reason"))}</small></li>' for x in tarama["dropped"]) + "</ul></details>")
        if tarama.get("sources"):
            p.append(f'<p class="note">{esc(S["sources"])}{esc(" · ".join(tarama["sources"]))}</p>')
        p.append("</section>")
        panels.append("".join(p))

    # Learning
    p = [f'<section class="panel" id="learning" aria-label="{esc(S["nav_learn"])}"><div class="p-head"><h2>{esc(S["plan"])}</h2>'
         f'<span class="soft">{esc(kisa_tarih(plan[0]["start"]) if plan else "")} – {esc(kisa_tarih(plan[-1]["end"]) if plan else "")}</span></div>']
    if cur:
        b0 = days(cur["start"])
        p.append(f'<div class="focus"><div class="label">{esc(S["to_start"].format(n=b0) if b0 > 0 else S["to_end"].format(n=days(cur["end"])))}</div>'
                 f'<h3>{link(cur["link"], esc(cur["name"])) or esc(cur["name"])}</h3><p>{esc(cur["scope"])}</p>'
                 + (f'<p class="goal"><b>{esc(S["when_done"])}</b> {esc(cur["done_when"])}</p>' if cur["done_when"] else "") + "</div>")
    if plan:
        p.append('<ol class="track">')
        for g in plan:
            st = "done" if g["status"] == "done" else "now" if g is cur else ""
            etiket = S["s_done"] if st == "done" else (S["s_now"] if (days(g["start"]) or 0) <= 0 else S["s_next"]) if st == "now" else ""
            nm = esc(g["name"].split(" (")[0])
            p.append(f'<li class="{st}"><span class="wk">{esc(S["week"].format(w=g["week"]) + etiket)}</span>'
                     f'<b>{link(g["link"], nm) or nm}</b><small>{esc(kisa_tarih(g["start"]))} – {esc(kisa_tarih(g["end"]))}</small></li>')
        p.append("</ol>")
    p.append(f'<ol class="week" aria-label="{esc(S["rhythm"])}">' + "".join(
        f'<li class="{"bos" if day_label(t, rit) == S["rest_short"] else esc(t)}{" today" if i == TODAY.weekday() else ""}"><b>{g}</b>{esc(day_label(t, rit))}</li>'
        for i, (g, t) in enumerate(zip(S["days_short"], rit["days"]))) + "</ol>")
    if rit["session"] or rit["note"]:
        p.append(f'<p class="note">{esc(". ".join(x for x in (rit["session"], rit["note"]) if x))}</p>')
    if sonra:
        p.append(f'<details class="fold"><summary>{esc(S["later"].format(n=len(sonra)))}</summary><ul class="plain">' + "".join(
            f'<li>{link(g["link"], esc(g["name"])) or esc(g["name"])}<small>{esc(" · ".join(x for x in (g["priority"], g["scope"]) if x))}</small></li>' for g in sonra) + "</ul></details>")
    p.append("</section>")
    panels.append("".join(p))

    # Open source (only when a GitHub user or a backlog file is configured)
    has_oss = bool(CFG["github_user"] or prog)
    if has_oss:
        m, o, ab, goal = gh["merged"], gh["open"], gh["important"], CFG["oss_goal"]
        p = [f'<section class="panel" id="oss" aria-label="{esc(S["oss"])}"><div class="p-head"><h2>{esc(S["oss"])}</h2>'
             f'{link(pr_url(), esc(S["pr_list"])) if CFG["github_user"] else ""}</div>']
        if CFG["github_user"]:
            sub = esc(S["goal_line"].format(g=goal, d=kisa_tarih(CFG["oss_deadline"]))) if goal else esc(S["merged"])
            p.append(f'<div class="card"><div class="big"><b class="mono">{m if m is not None else "?"}</b><span>{sub}</span></div>'
                     + (f'<div class="bar"><span style="width:{min(100, int(100 * (m or 0) / goal))}%"></span></div>' if goal else "")
                     + f'<p class="soft">{esc(S["oss_sub"].format(i=ab if ab is not None else "?", o=o if o is not None else "?"))}</p></div>')
        p.append('<div class="cards">')
        for pg in prog:
            pp = int(100 * pg["done"] / pg["total"]) if pg["total"] else 0
            p.append(f'<div class="card proj"><div class="proj-h"><b>{esc(pg["title"])}</b><span class="mono">{pg["done"]}/{pg["total"]}</span></div>'
                     f'<div class="bar thin"><span style="width:{pp}%"></span></div>'
                     + ("" if pg["done"] == pg["total"] else f'<small>{esc(S["next_x"].format(x=pg["next"]))}</small>') + "</div>")
        p.append("</div></section>")
        panels.append("".join(p))

    # Other: events, certifications, background jobs
    gelecek = [e for e in etk if not e["closed"] and (days(e["date_end"] or e["date"]) or 0) >= 0]
    gecmis = [e for e in etk if e not in gelecek]
    def ev(e):
        x = d(e["date"])
        tarih = f'<span class="date mono">{x.day}<small>{S["months"][x.month - 1]}</small></span>' if x else '<span class="date mono">—</span>'
        return (f'<li>{tarih}<div>{link(e["link"], esc(e["name"])) or esc(e["name"])}'
                f'<small>{esc(short(e["status"]))}' + (f' · {esc(S["reg_by"].format(d=kisa_tarih(e["register_by"])))}' if e["register_by"] else "") + "</small>"
                + (f'<details><summary>{esc(S["note"])}</summary><p>{esc(e["note"])}</p></details>' if e["note"] else "") + "</div></li>")
    p = ['<section class="panel" id="other" aria-label="' + esc(S["nav_other"]) + '"><div class="cards">'
         f'<section class="card"><h3>{esc(S["events"])} <span class="mono">{len(gelecek)}</span></h3>'
         + ('<ul class="events">' + "".join(ev(e) for e in gelecek) + "</ul>" if gelecek else f'<p class="empty">{esc(S["no_events"])}</p>')
         + (f'<details class="fold"><summary>{esc(S["past_events"].format(n=len(gecmis)))}</summary><ul class="events">' + "".join(ev(e) for e in gecmis) + "</ul></details>" if gecmis else "")
         + "</section>"]
    if ser:
        p.append(f'<section class="card"><h3>{esc(S["certs"])}</h3><ol class="certs">' + "".join(
            f'<li>{link(c["link"], esc(c["name"])) or esc(c["name"])}<small>{esc(" · ".join(x for x in (c["cost"], c["duration"], S["target"].format(d=kisa_tarih(c["target"])) if c["target"] else "", c["status"]) if x))}</small></li>'
            for c in ser) + "</ol></section>")
    if rut:
        p.append(f'<section class="card"><h3>{esc(S["jobs"])}</h3><pre>' + esc("\n".join(rut)) + "</pre></section>")
    p.append("</div></section>")
    panels.append("".join(p))

    bolumler = [("today", S["nav_today"]), ("applications", S["nav_apps"])] + ([("scan", S["nav_scan"])] if tarama else []) + \
               [("learning", S["nav_learn"])] + ([("oss", S["nav_oss"])] if has_oss else []) + [("other", S["nav_other"])]
    nav = "".join(f'<a href="#{i}">{esc(t)}</a>' for i, t in bolumler)
    title = esc(CFG["title"] or S["title"])
    sample = f'<p class="sample">{esc(S["sample"])}</p>' if (DATA / "SAMPLE").exists() else ""
    return (f'<!doctype html><html lang="{esc(CFG["lang"])}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>'
            f'<style>{CSS}</style></head>'
            f'<body><header><div class="bar-in"><h1>{title}</h1><span class="day">{esc(long_date(TODAY))}</span>'
            f'<nav aria-label="{esc(S["sections"])}">{nav}</nav><span class="meta mono" title="{esc(S["last_build"])}">{datetime.datetime.now().strftime("%H:%M")}</span></div></header>'
            f'<main class="wrap">{sample}{"".join(panels)}</main><script>{JS}</script></body></html>')

def render_md(bas, acik, kapali, ser, egt, plan, sonra, cur, etk, man, rit, gh, prog, rut, bugun, acil, odak, notlar, tarama):
    """README.md: the same content for the GitHub app / a phone."""
    q = lambda x: "?" if x is None else x
    md = [f"# {CFG['title'] or S['title']} — {long_date(TODAY)}\n",
          f"**{S['md_task'].format(tip=odak['tip'])}** " + (f"[{odak['baslik']}]({odak['link']})" if odak["link"] else odak["baslik"]) + (f" — {odak['alt']}" if odak["alt"] else "")]
    if notlar: md += ["", f"**{S['notes']}**"] + [f"- {n}" for n in notlar]
    md += [f"\n## {S['md_upcoming']}"]
    md += [f"- **{type_label(t)}:** {n} — {S['today'] if k == 0 else S['md_passed'] if k < 0 else S['in_days'].format(n=k)}" + (f" · [{S['md_open']}]({u})" if u else "")
           for t, n, k, u in bugun] or [f"- {S['nothing14']}"]
    md += [f"\n## {S['nav_apps']}", S["md_apps_head"], "|---|---|---|---|---|"]
    for b in acik + kapali:
        links = " · ".join(x for x in [f"[{S['l_posting']}]({b['posting']})" if b["posting"] else "", f"[{S['l_cv']}]({b['cv']})" if b["cv"] else "",
                                        f"[{S['l_package']}]({b['package']})" if b["package"] else ""] if x)
        yer = f" ({b['location']})" if b["location"] else ""
        md.append(f"| {b['company']}{yer} | {b['role']} | {b['deadline'] or '—'} | {b['status'] or S['st_' + stage(b)]} | {links} |")
    if tarama:
        md += [f"\n## {S['md_scan'].format(d=tarama.get('date', '—'))}", tarama.get("summary", "")]
        md += [f"- **{S['md_new']}:** {x.get('company')} — {x.get('role')}" + (f" · [{S['l_posting']}]({x['link']})" if x.get("link") else "") for x in tarama.get("new", [])]
        md += [f"- **{S['md_changed']}:** {x.get('company')} — {x.get('what')}" for x in tarama.get("changed", [])]
        md += [f"- **{S['md_closed']}:** {x.get('company')} — {x.get('reason')}" for x in tarama.get("closed", [])]
    md += [f"\n## {S['plan']}"]
    if rit["session"] or rit["note"]: md.append(S["md_rhythm"] + ". ".join(x for x in (rit["session"], rit["note"]) if x))
    md += ["", S["md_learn_head"], "|---|---|---|---|"]
    md += [f"| {g['week'] or '—'} | " + (f"[{g['name']}]({g['link']})" if g["link"] else g["name"]) + f" | {g['start'] + ' – ' + g['end'] if g['start'] else '—'} | {g['status'] or '—'} |" for g in egt]
    md += [f"\n## {S['waiting']}"] + [f"- [ ] {mm['task']}" + (f" ({', '.join(x for x in (mm['effort'], S['md_due'] + ': ' + mm['due'] if mm['due'] else '') if x)})" if mm["effort"] or mm["due"] else "")
                                      + (f" · [{S['md_open']}]({mm['link']})" if mm["link"] else "") for mm in man]
    if prog or CFG["github_user"]:
        md += [f"\n## {S['md_projects']}"] + [f"- **{p['title']}** {p['done']}/{p['total']} — {S['md_next']}: {p['next']}" for p in prog]
        if CFG["github_user"]:
            md.append("- " + S["md_oss"].format(m=q(gh["merged"]), g=f" / {CFG['oss_goal']}" if CFG["oss_goal"] else "", i=q(gh["important"]), o=q(gh["open"]))
                      + f" — [{S['pr_list']}]({pr_url()})")
    if etk:
        md += [f"\n## {S['events']}"] + [f"- {e['date']} — " + (f"[{e['name']}]({e['link']})" if e["link"] else e["name"]) + f" · {S['md_reg']}: {e['register_by'] or '—'} · {e['status'] or '—'}" for e in etk]
    if ser:
        md += [f"\n## {S['certs']}", S["md_cert_head"], "|---|---|---|---|---|"]
        md += [f"| {s['order']} | " + (f"[{s['name']}]({s['link']})" if s["link"] else s["name"]) + f" | {s['cost']} · {s['duration']} | {s['target'] or '—'} | {s['status'] or '—'} |" for s in ser]
    if rut: md += [f"\n## {S['jobs']}", "```", "\n".join(rut), "```"]
    return "\n".join(md) + "\n"

CSS = """
:root{--bg:#F4F5F7;--card:#FFFFFF;--sunk:#EAECEF;--ink:#15171B;--mut:#5A616B;--faint:#7C838E;--line:#DDE0E5;--acc:#1F4FC9;--acc-ink:#FFFFFF;--acc-soft:#E3EAFB;
--hot:#C2381F;--warm:#9A6200;--ok:#1D7A4C;--sent:#1F4FC9;--warn:#A86A00;--wait:#6B7280;--off:#9AA0A8;--hero:#15171B;--hero-ink:#ECEEF1;--hero-mut:#B4BAC4;--hero-acc:#F2B544;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--bg:#101215;--card:#181B20;--sunk:#1F2329;--ink:#ECEEF1;--mut:#A3A9B3;--faint:#80868F;--line:#262A31;--acc:#F2B544;--acc-ink:#101215;--acc-soft:#2A2416;
--hot:#FF7A5C;--warm:#F2B544;--ok:#6FD39A;--sent:#7CC4FF;--warn:#F2B544;--wait:#A3A9B3;--off:#5D636C;--hero:#181B20;--hero-ink:#ECEEF1;--hero-mut:#B4BAC4;--hero-acc:#F2B544;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.mono{font-family:ui-monospace,"Cascadia Mono",Consolas,Menlo,monospace;font-variant-numeric:tabular-nums}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:6px}
small{color:var(--mut);font-size:13px}.soft{color:var(--mut);font-size:14px}.empty{color:var(--mut);margin:0;font-size:14px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
header{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.bar-in{max-width:1240px;margin:0 auto;padding:12px 32px;display:flex;align-items:center;gap:16px}
h1{margin:0;font-size:18px;font-weight:700;letter-spacing:-.01em}
.day{color:var(--mut);font-size:14px;white-space:nowrap}
nav{display:flex;gap:4px;margin-left:auto;overflow-x:auto;scrollbar-width:none}nav::-webkit-scrollbar{display:none}
nav a{color:var(--mut);font-size:14px;padding:8px 14px;border-radius:8px;white-space:nowrap}nav a:hover{text-decoration:none;color:var(--ink);background:var(--sunk)}
nav a.on{background:var(--acc);color:var(--acc-ink);font-weight:600}
.meta{color:var(--faint);font-size:12.5px}
.wrap{max-width:1240px;margin:0 auto;padding:28px 32px 64px}
.js .panel{display:none}.js .panel.on{display:block}
.panel{display:block;margin-bottom:40px}.js .panel{margin-bottom:0}
.p-head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:0 0 18px}
h2{margin:0;font-size:24px;font-weight:650;letter-spacing:-.015em}
h3{margin:0 0 14px;font-size:15px;font-weight:600;display:flex;justify-content:space-between;align-items:baseline;gap:10px}
h3 .mono,h3 a{font-weight:400;font-size:13px;color:var(--mut)}h3 a{color:var(--acc)}
.label{font-family:ui-monospace,"Cascadia Mono",Consolas,Menlo,monospace;font-size:12.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--acc);margin-bottom:12px}
/* today */
.hero{background:var(--hero);color:var(--hero-ink);border:1px solid var(--line);border-radius:18px;padding:36px 40px;display:flex;gap:32px;flex-wrap:wrap;align-items:flex-end;justify-content:space-between}
.hero .label{color:var(--hero-acc)}
.hero-is{flex:1 1 520px;min-width:0}.hero h2{font-size:44px;line-height:1.08;letter-spacing:-.03em;font-weight:700;margin:0 0 12px}
.hero p{margin:0;color:var(--hero-mut);font-size:16.5px;line-height:1.55;max-width:62ch}
.hero-go{display:flex;flex-direction:column;align-items:flex-end;gap:14px}.hero-go .mono{color:var(--hero-mut);font-size:13.5px}
.go{display:inline-flex;align-items:center;min-height:44px;background:var(--hero-acc);color:#101215;padding:0 24px;border-radius:10px;font-weight:600;font-size:15px}.go:hover{text-decoration:none;filter:brightness(1.08)}
.acil{margin:16px 0 0;padding:12px 16px;border-radius:10px;background:var(--acc-soft);font-size:14.5px}.acil .mono{color:var(--hot);font-size:13px}
.notes{list-style:none;margin:16px 0 0;padding:0;display:flex;flex-direction:column;gap:4px}
.notes li{padding:2px 0 2px 18px;position:relative;font-size:14px;color:var(--mut)}.notes li::before{content:"";position:absolute;left:3px;top:10px;width:7px;height:7px;border-radius:50%;background:var(--warn)}
.strip-wrap{margin:24px 0 0;overflow-x:auto;scrollbar-width:thin}
.strip{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(14,minmax(78px,1fr));min-width:1092px;border-top:2px solid var(--ink)}
.gun{border-right:1px solid var(--line);padding:10px 8px 12px;min-height:128px;display:flex;flex-direction:column;gap:6px}.gun:last-child{border-right:0}
.gun.hs{background:color-mix(in srgb,var(--sunk) 45%,transparent)}.gun.today{background:var(--acc-soft)}
.g-ad{font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}.g-no{font-size:22px;line-height:1;font-weight:500}.today .g-no{color:var(--acc)}
.gun ul{list-style:none;margin:2px 0 0;padding:0;display:flex;flex-direction:column;gap:5px}
.ev{font-size:12px;line-height:1.3;padding:6px 7px;border-radius:6px;background:var(--sunk);overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
.ev a{color:var(--ink)}.ev.sert{background:var(--acc);color:var(--acc-ink)}.ev.sert a{color:var(--acc-ink)}.ev.past{background:var(--hot);color:#fff}.ev.past a{color:#fff}.ev small{display:block;color:inherit;opacity:.85;font-size:11px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-top:24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 24px;min-width:0}
.todo,.agenda,.events,.certs{list-style:none;margin:0;padding:0}
.todo li{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid var(--line);font-size:14.5px}.todo li:first-child,.agenda li:first-child,.events li:first-child,.certs li:first-child{border-top:0;padding-top:0}
.todo small{display:block}.due-s{flex:none;font-size:12.5px;color:var(--faint);padding-top:2px}.todo li.hot .due-s,.todo li.past .due-s{color:var(--hot);font-weight:500}.todo li.warm .due-s{color:var(--warm)}
.nums{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}.nums b{display:block;font-size:34px;font-weight:500;line-height:1.1}.nums span{color:var(--mut);font-size:13px}
.card p.soft{margin:0}
.agenda li{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid var(--line);font-size:14px}.agenda li a{color:var(--ink)}
.agenda .mono{flex:none;font-size:12.5px;color:var(--mut)}.agenda li.hot .mono,.agenda li.past .mono{color:var(--hot)}.agenda li.warm .mono{color:var(--warm)}
.type{display:block;color:var(--faint);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
.scan{margin-top:20px;padding:16px 4px 0;border-top:1px solid var(--line);display:flex;gap:10px 24px;flex-wrap:wrap;align-items:baseline;font-size:14px;color:var(--mut)}
.pill{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;font-size:12px;font-weight:600;background:var(--sunk);color:var(--mut)}.pill.s4,.pill.s5{background:var(--acc-soft);color:var(--acc)}.pill.s1,.pill.s2{color:var(--faint)}
.scan>b{color:var(--ink)}.scan b.mono{color:var(--ink);font-size:15px}.scan a{margin-left:auto;font-weight:600}.scan .warnline{color:var(--hot)}
.sample{margin:14px 0 0;padding:10px 14px;border:1px dashed var(--hot);border-radius:10px;color:var(--hot);font-size:14px}
/* applications */
.ara{margin-left:auto}.ara input{height:40px;width:260px;border:1px solid var(--line);border-radius:8px;padding:0 12px;font:inherit;font-size:14px;background:var(--card);color:var(--ink)}
.board{display:flex;gap:16px;overflow-x:auto;padding-bottom:8px;align-items:flex-start}
.col{flex:1 0 250px;background:var(--sunk);border-radius:14px;padding:14px}
.col h3{margin:0;font-size:12.5px;text-transform:uppercase;letter-spacing:.07em}.col-alt{margin:2px 0 12px;font-size:12.5px;color:var(--faint)}
.col.process{background:var(--acc-soft)}.col.decide,.col.watching{background:none;border:1px dashed var(--line)}
.kart{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:0 0 10px;position:relative}
.kart summary{list-style:none;cursor:pointer;padding:12px 14px;display:flex;flex-direction:column;gap:2px;border-radius:10px}.kart summary::-webkit-details-marker{display:none}
.kart summary:hover{border-color:var(--acc)}.kart:hover{border-color:color-mix(in srgb,var(--acc) 50%,var(--line))}
.k-ust{display:flex;align-items:baseline;gap:8px}.k-ust b{font-weight:600;font-size:15px}
.chip{margin-left:auto;font-size:12px;color:var(--mut);white-space:nowrap}.chip.hot,.chip.past{color:var(--hot)}.chip.warm{color:var(--warm)}
.k-rol{color:var(--mut);font-size:13.5px}.k-st{font-size:12.5px;color:var(--faint)}
.new{font-style:normal;font-size:11px;font-weight:600;color:var(--acc-ink);background:var(--acc);padding:1px 6px;border-radius:999px}
.detail{padding:0 14px 14px;font-size:13.5px;color:var(--mut)}.detail p{margin:0 0 6px}.kontrol{font-size:12.5px;color:var(--faint)}
.links{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}.links a{font-size:13px;font-weight:600;border:1px solid var(--line);border-radius:6px;padding:5px 12px}.links a:hover{border-color:var(--acc);text-decoration:none}
.kart.gizli{display:none}
details.fold{margin:16px 0 0}details.fold>summary{cursor:pointer;color:var(--mut);font-size:14px;padding:8px 0}details.fold>summary:hover{color:var(--ink)}
.closed-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;margin-top:8px}.closed-grid .kart{margin:0;opacity:.75}
/* scan, learning, oss, other */
.lead{margin:0 0 4px;color:var(--mut);max-width:80ch}.tcol ul,ul.plain{list-style:none;margin:0;padding:0}.tcol li,ul.plain li{padding:8px 0;border-top:1px solid var(--line);font-size:14px}.tcol small,ul.plain small{display:block}
.focus{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 24px;margin-bottom:20px}.focus h3{font-size:19px;margin-bottom:8px}.focus h3 a{color:var(--ink);font-size:inherit}
.focus p{margin:0 0 6px;font-size:14.5px;color:var(--mut)}.focus .goal{color:var(--ink);margin:0}
.track{list-style:none;margin:0 0 16px;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.track li{border-top:3px solid var(--line);padding:9px 2px 0;font-size:13.5px;line-height:1.35}.track li b{display:block;font-weight:600;margin:3px 0}.track li b a{color:var(--ink)}
.track .wk{font-size:12.5px;color:var(--faint)}.track li.now{border-color:var(--acc)}.track li.now .wk{color:var(--acc);font-weight:600}.track li.done{border-color:var(--ok)}.track li.done b a{color:var(--mut)}
.week{list-style:none;margin:8px 0 0;padding:0;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px}
.week li{padding:8px 10px;border-radius:8px;background:var(--card);border:1px solid var(--line);font-size:12.5px;color:var(--mut)}.week li b{display:block;color:var(--ink);font-weight:600;font-size:13px}
.week li.bos{background:none;border-style:dashed}.week li.today{border-color:var(--acc);box-shadow:inset 0 0 0 1px var(--acc)}
.note{font-size:13.5px;color:var(--mut);margin:14px 0 0}
.big{display:flex;align-items:baseline;gap:10px}.big b{font-size:44px;font-weight:500;line-height:1}.big span{color:var(--mut);font-size:14px}
.bar{height:6px;background:var(--sunk);border-radius:3px;overflow:hidden;margin:14px 0 10px}.bar span{display:block;height:100%;background:var(--acc)}.bar.thin{height:4px;margin:8px 0 6px}
.proj-h{display:flex;justify-content:space-between;gap:12px;font-size:14.5px}.proj-h .mono{color:var(--mut);font-size:13px}.proj small{display:block}
.events li{display:flex;gap:14px;padding:10px 0;border-top:1px solid var(--line)}.events li>div{min-width:0}
.date{flex:none;width:36px;text-align:center;font-size:18px;line-height:1.1}.date small{display:block;font-size:11.5px}
.events a,.certs a{display:block;color:var(--ink);font-size:14px;font-weight:500}.events small,.certs small{display:block}
.events details summary{cursor:pointer;font-size:12.5px;color:var(--faint);margin-top:2px}.events details p{margin:4px 0 0;font-size:13px;color:var(--mut)}
.certs li{padding:9px 0;border-top:1px solid var(--line)}
pre{font:11.5px/1.5 ui-monospace,"Cascadia Mono",Consolas,Menlo,monospace;overflow:auto;white-space:pre-wrap;margin:0 0 10px;color:var(--mut)}
@media(max-width:900px){.bar-in{flex-wrap:wrap;gap:4px 14px}nav{order:3;width:100%;margin:0 -6px}.meta{margin-left:auto}.hero h2{font-size:34px}}
@media(max-width:640px){.bar-in,.wrap{padding-left:16px;padding-right:16px}.wrap{padding-top:18px}.hero{padding:24px 20px;border-radius:14px}.hero h2{font-size:28px}
.hero-go{align-items:flex-start;width:100%}.cards{grid-template-columns:1fr}.board{flex-direction:column;overflow:visible}.col{flex:none;width:100%}
.ara{margin-left:0;width:100%}.ara input{width:100%}.week{grid-template-columns:repeat(4,minmax(0,1fr))}.scan a{margin-left:0}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
"""

JS = """
(function(){
  document.documentElement.classList.add('js');
  var links=[].slice.call(document.querySelectorAll('nav a')),ids=links.map(function(a){return a.getAttribute('href').slice(1)});
  function show(){
    var h=location.hash.slice(1),el=h&&document.getElementById(h),id='today';
    if(el){var p=el.closest('.panel');if(p)id=p.id}
    document.querySelectorAll('.panel').forEach(function(p){p.classList.toggle('on',p.id===id)});
    links.forEach(function(a,i){var on=ids[i]===id;a.classList.toggle('on',on);if(on)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});
    if(el&&el.id!==id)el.scrollIntoView();else scrollTo(0,0);
  }
  addEventListener('hashchange',show);show();
  var box=document.getElementById('search'),lang=document.documentElement.lang;
  if(box)box.addEventListener('input',function(){var q=box.value.trim().toLocaleLowerCase(lang);
    document.querySelectorAll('.kart').forEach(function(k){k.classList.toggle('gizli',!!q&&k.dataset.ara.indexOf(q)<0)})});
})();
"""

def init(dest=None):
    """First setup: config.json, profile.json and a data/ folder copied from the examples. Existing files are kept."""
    here = pathlib.Path(__file__).parent
    dest = pathlib.Path(dest) if dest else here
    dest.mkdir(parents=True, exist_ok=True)
    made = []
    if not (dest / "config.json").exists():
        cfg = json.loads((here / "config.example.json").read_text(encoding="utf-8"))
        cfg.update(data_dir="data", backlog="data/backlog.md", status_log="data/jobs.log")
        (dest / "config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8"); made.append("config.json")
    if not (dest / "profile.json").exists():
        shutil.copy(here / "profile.example.json", dest / "profile.json"); made.append("profile.json")
    if not (dest / "data").exists():
        shutil.copytree(here / "example-data", dest / "data"); made.append("data/")
        (dest / "data" / "SAMPLE").write_text("delete this file once data/ holds your own records; the dashboard shows a sample-data notice while it exists\n", encoding="utf-8")
    print(("created: " + ", ".join(made)) if made else "nothing to do: config.json, profile.json and data/ exist")
    return made

def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the tracker dashboard (index.html + README.md) from JSON files.")
    ap.add_argument("--config", help="config JSON (see config.example.json)")
    ap.add_argument("--data", help="data folder (overrides data_dir)")
    ap.add_argument("--out", help="output folder (overrides out_dir)")
    ap.add_argument("--lang", choices=sorted(STR), help="label language (overrides lang)")
    ap.add_argument("--today", type=datetime.date.fromisoformat, help="pretend today is YYYY-MM-DD (demos, tests)")
    ap.add_argument("--init", nargs="?", const="", metavar="DIR", help="create config.json, profile.json and data/ from the examples (in DIR, default here)")
    a = ap.parse_args(argv)
    if a.init is not None:
        return init(a.init or None)
    build(load_config(a.config, data_dir=a.data, out_dir=a.out, lang=a.lang), a.today)

if __name__ == "__main__":
    main()
