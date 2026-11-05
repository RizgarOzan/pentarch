---
name: cv
description: Draft or check a one-page CV from the tracker's profile.json and a job posting, in XYZ bullet form, then run the rule checker. Use when the user wants a CV or resume for a posting, asks to fix an existing one, or asks why a CV would not pass an ATS.
---

# CV

You write the draft. The user sends it. Nothing here opens a job board or submits anything.

Write the CV in `cv.language` from the tracker's `profile.json`; if there is no profile, the language the user writes in. Instructions below are English; the output is not.

Tool: `skills/cv/cv.py` next to this folder. Stdlib only.

```
python skills/cv/cv.py template                          # the one-column skeleton to fill in
python skills/cv/cv.py check cv.md                       # FAIL / WARN / PASS lines, exit 1 on FAIL
python skills/cv/cv.py check cv.md --jd posting.txt      # also keyword overlap with the posting
python skills/cv/cv.py check cv.md --lang tr             # skips the English grammar checks
```

## Steps

1. Read the `cv` block of `profile.json` (`language`, `format`, `sections`, `max_pages`, `highlight`, `avoid`) and the posting. Ask for the posting if there is none: a CV not aimed at a posting is a worse CV.
2. Ask for the facts you do not have: employers, dates, what changed and by how much. Never invent a number, an employer or a date. A bullet with no number stays a draft with `[number?]` in it until the user fills it.
3. Start from `python skills/cv/cv.py template`. Keep the section order in `cv.sections`.
4. Write every bullet in XYZ form: "Accomplished [X] as measured by [Y], by doing [Z]". Past-tense verb first, a number in the bullet, the method last. The first bullet of every role carries a number.
5. Pull the posting's own words into the Skills section and the bullets, spelled as the posting spells them. Do not add a skill the user does not have.
6. Save to `cv.md` and run `python skills/cv/cv.py check cv.md --jd posting.txt`. Fix every FAIL. Read every WARN and fix it or tell the user why it stays.
7. Give the user the markdown. It converts to a plain single-column PDF with any markdown tool; say that the PDF is what gets sent, and that it must stay one column with no graphics.

## Rules the checker enforces

Each rule names its source. "Bock" is Laszlo Bock's XYZ formula as quoted by Simplify; "Harvard" is the Harvard OCS resume guide; "HRBrain" is its ATS writeup; "Jake's" is Jake's Resume template; "Pirate King" and "2026 hiring" are two recruiter videos; "Simplify" is Simplify's resume guide.

| rule | level | source |
|---|---|---|
| bullet = past-tense action verb + number + method | FAIL on first bullet without a number, WARN on the rest | Bock, 2026 hiring |
| no I / we / my, no passive, no "responsible for", "member of", "helped with" | FAIL (pronoun, duty phrase), WARN (passive) | Harvard, Bock |
| 3 to 5 bullets per role, each verb used once | WARN | Harvard, Simplify |
| headings only from: Experience, Work Experience, Education, Skills, Technical Skills, Projects, Certifications, Publications, Leadership, Awards (and their Turkish forms) | FAIL | HRBrain |
| order Education, Experience, Projects, Technical Skills | PASS note when kept | Jake's |
| one page: about 60 lines or 4200 characters of markdown | WARN | Jake's, Pirate King, Harvard |
| contact line: email, phone, LinkedIn and GitHub links | FAIL on no email, WARN on the rest | Jake's, Pirate King |
| no tables, images, columns, photo, decorative glyphs | FAIL (table, image), WARN (glyphs) | HRBrain, 2026 hiring |
| dates as `Mon. YYYY -- Mon. YYYY` or `-- Present`, never first on a line | WARN | Jake's, HRBrain |
| entries newest first | WARN | Harvard |
| no age, gender or marital status | WARN | Harvard |
| no obvious tools (Word, email), no soft-skill lists, no "intermediate"/"familiar with" labels in Skills | WARN | Pirate King, 2026 hiring |
| no summary / objective paragraph | WARN | Pirate King |
| bullets under 220 characters, no trailing period | WARN | Harvard |
| posting keywords, weighted preferred > requirements > responsibilities: under half present is a WARN; a keyword repeated 4+ times is a stuffing note | WARN | 2026 hiring, HRBrain |

## Where the sources disagree

Tell the user these are judgement calls and which side the checker took.

- **Experience above Education** (Pirate King, for anyone past their first job) vs Education first (Jake's). The checker only notes Jake's order; put Experience first once the user has one real role.
- **Skills first** (Pirate King) vs Skills last (Jake's). Default to last; move up when the posting is tool-heavy.
- **One page always** (Pirate King, Jake's) vs two pages after about ten years (Harvard). The checker warns past one page; keep two only with a decade of relevant work.
- **GPA**: Jake's shows it, Harvard says only above 3.5. Include it only when high and recent.
- **File format**: HRBrain says PDF or .docx, some ATS vendors prefer .docx. Send PDF unless the posting says otherwise.
- **Right-aligned dates**: Jake's does it, HRBrain warns that some parsers read columns wrong. In markdown, keep the date on the same line as the title, separated by spaces.
- **Prose vs bullets**: Harvard allows short prose for research roles. The checker expects bullets.
- **Summary**: Pirate King says never, 2026 hiring allows two lines for career changers. The checker warns; keep it only for a change of field.

## Keep out of the CV

Anything from `cv.avoid`. The user's address beyond city and country. A photo. References. Hobbies. Anything you could not point to a link or a number for.
