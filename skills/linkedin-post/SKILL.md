---
name: linkedin-post
description: Draft, rewrite or check a LinkedIn post (hook, length, voice, AI tells) and log it so hook formulas can be measured against the user's own reach. Use when the user wants to write a LinkedIn post, fix one, pick a hook, plan a posting week, or asks "why did this post not land".
---

# LinkedIn post

You write drafts. The user posts. Nothing in this skill opens LinkedIn or sends anything.

Write the post in the user's language: `cv.language` in the tracker's `profile.json` if it exists, otherwise the language the user writes in. Instructions below are English; the output is not.

Tools: `skills/linkedin/li.py` next to this folder. Stdlib only.

## Steps

1. **Voice first.** Ask for 3 to 5 posts the user already wrote, or messages they sent, or the `about` text in their profile. Note sentence length, how they open, whether they use "I" or "we", which words they never use. Keep that note in the thread; every draft is checked against it. Done when you can name two things that make their writing theirs.
2. **One idea.** Make the user say the point in one sentence. If it needs "and", it is two posts. Done when the one-sentence version exists.
3. **Pick the pillar and the hook.** Pillar from the table below, hook formula from `hooks.md` in this folder. If `python skills/linkedin/li.py log stats` has 5 or more results for this user, prefer the formulas and pillars with the highest average views for them; the market defaults only apply while the log is empty. Done when both are named before any body text is written.
4. **Draft.** Hook line, blank line, one thought per line, blank line between thoughts, close with a question the reader can answer in one sentence. Write it plainly, in the user's voice from step 1.
5. **Check.** Save to a file and run `python skills/linkedin/li.py check post.txt`. Fix every WARN you agree with; say which you left and why. Read the fold preview line aloud: it is the only thing most readers see. Done when the check prints no FAIL and the fold preview makes sense on its own.
6. **Ask three questions before handing it over.** Would the user say this sentence out loud to a colleague? Is there one number or one concrete scene? Could anyone else have posted this word for word? Fix what fails.
7. **Log it.** `python skills/linkedin/li.py log add --hook "<formula>" --pillar <pillar> --file post.txt`. Tell the user the id and ask them to come back in 48 hours with views and comments: `python skills/linkedin/li.py log result <id> --views N --comments N`. Done when the id is in the reply.

When the user asks why a post did not land: run `python skills/linkedin/li.py check` on it, compare its hook formula and pillar with `python skills/linkedin/li.py log stats`, and look at the first 210 characters first. Most failures are a hook that is a label, not a claim.

## Pillars

| pillar | what it is | share of posts |
|---|---|---|
| authority | something you did or learned, with a number or a result | 40 to 50% |
| narrative | a story with a turn: before, what changed, after | 30 to 40% |
| community | a question, a thank-you, a comment on someone else's work | 20 to 30% |

Shares are a convention, unverified. Rebalance from `log stats` once there is data.

## Job-search tie-in

If the tracker's `data_dir` (from its `config.json`, default `data/`) holds `applications.json` or `scan.json`:
- An application in stage `sent` or `process`: offer an authority post about something related to that company's domain, never naming the application or the company's hiring process.
- A new company in `scan.json`: offer a comment draft on one of their recent posts before the user applies (see `linkedin-network`).
- A `closed` application with feedback: offer a narrative post about the lesson, with the company name left out.

## Rules, with their status

- Post limit 3,000 characters. [fact: LinkedIn Help, "Character limits for posts"]
- The feed shows about the first 210 characters, then "...see more". [convention, unverified; depends on device and font]
- 900 to 1,300 characters. [convention, unverified]
- One link in the body lowers reach, put it in the first comment. [convention, unverified; LinkedIn has not confirmed it]
- 0 to 3 hashtags. [convention, unverified]
- Tuesday to Thursday mornings in the reader's timezone. [convention, unverified; the user's own log beats this]
- 3 to 4 posts a week, never two of the same pillar in a row. [convention]

## Weekly plan

Sunday, 20 minutes: pick 3 to 4 ideas, one sentence each, assign pillar and hook, write the hooks only. Weekday mornings: expand one hook into a post, check, log. Saturday: enter results for the week's posts, read `log stats`, drop the formula with the lowest average and try one you have not used.

## Words to keep out

`python skills/linkedin/li.py check` lists AI-tell phrases and plainer replacements in both languages. The rule behind the list: if a phrase would be odd in a message to a friend, it is odd in a post. Contrast framings ("it's not X, it's Y"), triads of adjectives, em dashes and announcement openers ("thrilled to share", "heyecanla paylaşıyorum") are the ones that mark a post as generated fastest.
