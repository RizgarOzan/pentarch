---
name: konsey
description: Puts one idea, plan or decision in front of four advisors who work independently (Advocate, Skeptic, Employer, Builder) and a judge, returns a single verdict - BUILD, FIX FIRST or KILL - with the main risk and a 10-minute test, and records it in the notes folder. Only runs when the user types /konsey.
disable-model-invocation: true
argument-hint: <idea, plan or decision>
---

# Konsey

The idea is `$ARGUMENTS`. If that is empty, ask the user for it in one sentence and wait.

This is not the Telegram `council:` vote (that one asks several models and counts votes). Here five Claude Code subagents look at one idea from fixed angles and a judge picks a verdict. It needs the five `konsey-*` agents in `~/.claude/agents/`; Pentarch's setup copies them there.

Notes folder: `{{NOTES}}`. Assistant home: `{{HOME}}`. If either still reads as a `{{...}}` placeholder, take `notes_dir` from `~/.pentarch/pentarch.json` and use `~/.pentarch` as the home. Files used:
- `{{HOME}}/profile.md`: who the user is, goals, weekly hours, projects.
- `{{NOTES}}/konsey.md`: past verdicts. Create it if it is missing, with a `# Konsey` heading and a `<!-- entries -->` line.
- `{{NOTES}}/log.md`: activity log, only if it already exists.
Never touch a `raw/` folder.

Answer in the user's language. The labels below are English; translate them when the user writes another language.

## 1. Write the brief

You run the council; the advisors only see what you give them.

1. Pick a short kebab-case slug for the idea, e.g. `cli-vs-web-app`.
2. Search `konsey.md` for the slug and the idea's main nouns. If the idea was judged before, note the date, verdict, risk and test.
3. Read `profile.md` and no more than two notes that matter for this idea. Skip the rest.
4. Ask the user at most two short questions, and only if the goal (getting hired, learning, a product, money) or the constraint (weekly hours, a deadline) is still unclear.
5. Write the brief in under 600 words, in neutral language:
   - What the idea is, in plain words.
   - The user's situation: their goals and target roles, their weekly time budget, and related work they have already done, with measured numbers only.
   - Local paths to that work, so `konsey-uygulayici` can read the code.
   - Previous verdict on this idea, if there is one.
   Every statement about the user must come from a file you opened in this run. Do not guess or fill gaps. Remove any excitement, self-praise or loaded wording the user used, so no advisor can tell which answer the user is hoping for.

## 2. Run the advisors

Start `konsey-savunucu`, `konsey-supheci`, `konsey-isveren` and `konsey-uygulayici` together, in one message with four subagent calls. Give each the same brief and nothing more. No advisor ever sees another's report.

## 3. Run the judge

Start `konsey-hakim` with the brief and the four reports, each labelled with its role.

## 4. Record it

In `konsey.md`, put the judge's log block right under the `<!-- entries -->` marker, so the newest entry is first. Use one targeted edit. If `log.md` exists, add this line at the top of its entries:
`- YYYY-MM-DD konsey: <slug> -> <VERDICT>`
Do not rewrite either file. If `konsey.md` now has more than 40 entries, tell the user the older ones could be folded into a summary, but leave that for them to ask for.

## 5. Answer the user

Show the judge's verdict block and nothing else. Share the advisor reports only if the user asks. Add no comments of your own and do not soften the verdict.
