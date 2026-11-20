"""Recruiter replies: mail that looks like an answer to a tracked application becomes a Yes/No to move that row.

Pure matching, no model: a mail line (`Name <addr> | subject | start of the text`) counts when it names a company the
tracker holds in the stage "sent" or "process". The proposal text is built here from the tracker's own words; nothing
the sender wrote goes into it, and nothing moves before the owner's yes.
    rejected -> closed     interview -> process     offer -> decide
"""
import re

RED = re.compile(r"unfortunately|regret to inform|not (?:be )?moving forward|other candidates|not selected|will not be proceeding|"
                 r"maalesef|olumsuz|değerlendirmeye alınma|leider|absage|malheureusement|lamentablemente", re.I)
OFFER = re.compile(r"pleased to offer|offer letter|job offer|iş teklifi|teklif mektubu|jobangebot|offre d'emploi", re.I)
GORUSME = re.compile(r"interview|schedule a (?:call|chat)|mülakat|görüşme|vorstellungsgespräch|entretien|entrevista", re.I)
GECERLI = {"sent": ("closed", "process", "decide"), "process": ("closed", "decide")}


def sinifla(metin):
    """The stage a reply points to, or None. A rejection wins when a mail mentions both."""
    if RED.search(metin):
        return "closed"
    if OFFER.search(metin):
        return "decide"
    if GORUSME.search(metin):
        return "process"
    return None


def _ad(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower().translate(str.maketrans("çğıöşü", "cgiosu")))


def oneriler(satirlar, kayitlar):
    """[(id, company, stage)] for mail lines that answer an open application. One proposal per application."""
    out = {}
    for satir in satirlar:
        hedef = sinifla(satir)
        if not hedef:
            continue
        duz = _ad(satir)
        for r in kayitlar:
            sirket = _ad(r.get("company") or "")
            if len(sirket) < 3 or sirket not in duz or hedef not in GECERLI.get(r.get("stage"), ()):
                continue
            out.setdefault(r["id"], (r["id"], r["company"], hedef))
    return list(out.values())
