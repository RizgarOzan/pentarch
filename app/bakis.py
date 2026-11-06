"""Perspective presets for the council: each seat can take a different point of view for one question.
Pick them by name or by pack, e.g. 'tester,hr' or 'kod'. Unknown names are ignored."""
from config import T

BAKIS = {
    "tester": ("Testçisin: bu nasıl bozulur, hangi girdi ve kenar durumu denenmemiş, nasıl doğrulanır onu söyle.",
               "You are the tester: how this breaks, which inputs and edge cases are untried, how to verify it."),
    "debugger": ("Hata ayıklayıcısın: belirtiden kök nedene git, en ucuz tekrar üretme yolunu ve ilk bakılacak yeri söyle.",
                 "You are the debugger: go from symptom to root cause, name the cheapest repro and where to look first."),
    "reviewer": ("Kod gözden geçirenisin: hata, güvenlik açığı ve gereksiz karmaşıklık ara; her bulguya yer ve düzeltme yaz.",
                 "You are the code reviewer: look for bugs, security holes and needless complexity; give location and fix."),
    "coder": ("Kodlayansın: en küçük çalışan çözümü, hangi dosyaya ne yazılacağını ve kaç saat süreceğini söyle.",
              "You are the coder: the smallest working solution, what goes in which file, and how many hours it takes."),
    "designer": ("Tasarımcısın: kullanıcı ekranda ilk neyi görür, nerede takılır, neyi kaldırmak gerekir.",
                 "You are the designer: what the user sees first, where they get stuck, what should be removed."),
    "researcher": ("Kullanıcı araştırmacısısın: varsayımı kanıttan ayır, kime hangi soruyla nasıl doğrulanacağını söyle.",
                   "You are the user researcher: separate assumptions from evidence, say whom to ask what to verify it."),
    "persona": ("Hedef kitlenin ta kendisisin: soruda geçen kitleden biri gibi düşün (kitle yazmıyorsa en olası kullanıcı). "
                "Buna para/zaman verir miydin, neden?",
                "You are the target audience: think as one person from the audience in the question (or the likeliest user). "
                "Would you spend money/time on this, and why?"),
    "hr": ("İşe alımcısın (HR): CV'yi ya da başvuruyu 30 saniyede elersin; neye takılırsın, neyi görmek istersin, mülakata çağırır mısın.",
           "You are the recruiter (HR): you screen in 30 seconds; what bothers you, what you want to see, would you interview."),
    "hiring-manager": ("Ekip lideri olarak işe alıyorsun: bu kişi ilk ayda ne teslim eder, hangi beceri eksik.",
                       "You are the hiring manager: what this person ships in month one, which skill is missing."),
    "writer": ("Metin yazarısın: mail ya da metin kısa, insan gibi, tek net isteğe sahip mi; daha iyi bir taslak öner.",
               "You are the writer: is the mail or text short, human, with one clear ask; propose a better draft."),
    "ideas": ("Fikir avcısısın: sahibinin becerilerine ve elindeki projelere uyan, küçük başlayıp büyüyebilecek 3 somut proje öner.",
              "You are the idea scout: propose 3 concrete projects that fit the owner's skills and current work, small to start."),
    "marketer": ("Pazarlamacısın: bunu kim, hangi kanaldan, hangi cümleyle duyar; rakip ne diyor.",
                 "You are the marketer: who hears about this, on which channel, with what line; what competitors say."),
    "security": ("Güvenlikçisin: veri nereye gidiyor, kim kötüye kullanır, en ucuz koruma ne.",
                 "You are the security engineer: where data goes, who abuses it, the cheapest protection."),
    "sceptic": ("Şüphecisin: bu işin neden boşa gideceğini, kimin zaten yaptığını, gözden kaçanı ara.",
                "You are the sceptic: why this will be wasted effort, who already does it, what is being missed."),
}
PAKET = {
    "kod": ["coder", "tester", "debugger", "reviewer", "security"],
    "urun": ["designer", "researcher", "persona", "marketer", "sceptic"],
    "is": ["hr", "hiring-manager", "writer", "persona", "sceptic"],
    "mail": ["writer", "persona", "sceptic"],
    "fikir": ["ideas", "persona", "marketer", "coder", "sceptic"],
}
PAKET.update(code=PAKET["kod"], product=PAKET["urun"], job=PAKET["is"], idea=PAKET["fikir"])


def sec(metin):
    """'kod' or 'tester,hr' -> list of (name, role text). Empty or unknown -> []."""
    adlar = []
    for p in (metin or "").replace(" ", "").lower().split(","):
        adlar += PAKET.get(p, [p])
    return [(a, T(*BAKIS[a])) for a in dict.fromkeys(adlar) if a in BAKIS]


def liste():
    return (", ".join(BAKIS) + "\n" + T("Paketler: ", "Packs: ")
            + "; ".join(f"{k}={'+'.join(v)}" for k, v in PAKET.items() if k not in ("code", "product", "job", "idea")))
