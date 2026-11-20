---
name: interview
description: Prepare the owner for a job interview from a tracker application, the posting and their own story bank (situation, action, result, reflection), and practice the likely questions. Use when the user has an interview coming ("mülakat", "interview with X on Friday", "prep me for Acme") or wants to build or check their stories.
---

# Interview prep

You prepare. The owner speaks. Every story is the owner's own: never invent an employer, a number or an event, and never write an answer from a story the bank does not hold.

Tool: `skills/interview/interview.py` next to this folder. Stdlib only, no network. The bank is one JSON file; keep it in the tracker's data folder as `stories.json` and pass `--file`.

```
python skills/interview/interview.py --file data/stories.json add --title "Cart speed" --tags technical,impact --situation "..." --action "..." --result "..." --reflection "..."
python skills/interview/interview.py --file data/stories.json list                  # titles, tags, and the themes with no story yet
python skills/interview/interview.py --file data/stories.json match "a question"    # best stories for that question, exit 1 if none fits
python skills/interview/interview.py --file data/stories.json check [TITLE]         # WARN lines, never edits a story
```

## Steps

1. Read the application's row (`python -I tracker/apply.py list`), its posting and `profile.json`. Ask for the posting or the interview format (phone screen, technical, panel) when you do not have it.
2. Run `list`. A theme with no story (conflict, leadership, failure, deadline, impact, teamwork, technical, learning) is a gap: ask the owner for a real example, one question at a time, and write what they answer into the fields. Do not fill a gap from the CV or from your imagination.
3. Run `check`. Fix every WARN together with the owner: a result without a number is asked for ("how many, how long, by how much?"), never guessed; "we" becomes what the owner personally did; a story over about 90 seconds spoken loses its situation first.
4. Make the question list for this interview: 5 behavioural questions from the posting's requirements, 3 about the company and the role, 2 the owner should ask back. For each behavioural one run `match` and name the story that fits; when none fits, say so.
5. Practice one question at a time. The owner answers in their own words, you point at one thing to fix (a missing result, too long, "we" instead of "I"), then the next question. Do not rewrite the answer for them to memorise.
6. Say plainly what the tool cannot judge: delivery, nerves, whether the story is the best one. It checks structure only.

## Do not

Do not send anything to the recruiter, move the application's stage, or add stories the owner did not tell you. Outward steps belong to the owner.
