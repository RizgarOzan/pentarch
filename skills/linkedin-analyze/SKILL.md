---
name: linkedin-analyze
description: Read the user's own LinkedIn numbers (post log, profile score, network log) and say what to change next week. Use when the user asks what is working on LinkedIn, which posts got reach, whether the profile improved, or wants a weekly or monthly LinkedIn review.
---

# LinkedIn analyze

Read-only. This skill reads the three state files and the tracker, prints a review, and proposes next week's plan. It changes nothing and opens nothing.

Output in the user's language (`cv.language` in the tracker's `profile.json`, else the language they write in).

Tool: `python skills/linkedin/li.py`. State under the Pentarch home, `linkedin/`:

| file | written by | what it holds |
|---|---|---|
| `log.json` | `python skills/linkedin/li.py log add`, `log result` | each post: date, hook formula, pillar, chars, views, comments, reactions |
| `network.json` | `python skills/linkedin/li.py network add`, `touch` | each contact: company, why, touches, next follow-up |
| a profile export JSON | the user, by hand | the fields `python skills/linkedin/li.py profile` scores |

## Steps

1. **Fill the gaps first.** Run `python skills/linkedin/li.py log stats`. Posts without results are not in the stats. List their ids and ask the user for views and comments before reading anything else. Done when every post older than 48 hours has a result or the user says it is lost.
2. **Posts.** From `log stats`: best and worst hook formula by average views, best pillar, and the number of posts behind each average. With fewer than 3 posts per formula, say "too early" for that row instead of a conclusion. Then compare comments per view: a post with high views and no comments had a hook that worked and a close that did not. Done when the reply names one formula to keep, one to drop, and one untried formula from `linkedin-post/hooks.md` to test.
3. **Profile.** If the user has a profile export, run `python skills/linkedin/li.py profile` and compare the total with the last review's total (keep the previous number in the thread or ask). Done when the delta and the three lowest rows are in the reply.
4. **Network.** Run `python skills/linkedin/li.py network due`. Count contacts with 0 touches older than 14 days: those are drafts that were never sent, ask whether to drop them. Count replies (the user tells you, there is no field for it; add it to `--note`). Done when the reply has: due now, never touched, replied this month.
5. **Job search link.** Read `applications.json` from the tracker's `data_dir`. For each application in `sent` or `process`, check whether the company has a contact in `network.json`. Companies with an open application and no contact go to the top of next week's plan. Done when that list is in the reply.
6. **Next week in five lines.** Three post ideas (pillar + hook formula + one sentence), two outreach actions (person or company + what), one profile fix. Based on steps 2 to 5, not on general advice. Done when each line traces to a number from this review.

## How to read the numbers

- Views are the hook. Comments are the close. Reactions are neither, ignore them unless they are the only data.
- Compare the user with the user. A 300-view post is a win for someone who had 80 last month. There are no public benchmarks worth quoting here; the market numbers people cite are from unknown samples. [convention, unverified]
- Day and hour: `log.json` stores the date only. If the user wants timing data, ask them to add the hour in `--date` as `YYYY-MM-DD HH`; the stats ignore it, you read it by hand.
- Five posts is the smallest set that says anything. Below that, the review is a checklist, not an analysis. Say so.
- One post that did very well skews the average. Mention the median when one post holds more than half the views.

## Monthly version

Same steps, plus: pillar shares versus the 40/30/20 convention in `linkedin-post`, profile total trend over the month, contacts added versus contacts that replied, and whether any application in the tracker moved to `process` after a contact was touched (the user has to tell you; note it in `--note` so next month it is in the file).

## Output shape

A short table for posts (formula, n, avg views, avg comments), three lines for profile, three lines for network, then the five-line plan. Under 40 lines total. Numbers in the table, not in sentences.
