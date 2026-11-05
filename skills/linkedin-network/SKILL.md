---
name: linkedin-network
description: Draft LinkedIn comments, connection notes and recruiter messages tied to the user's open applications and scanned companies, and keep a contact log with follow-up dates. Use when the user asks who to reach out to, what to write to a recruiter or hiring manager, how to comment on a company's post, or what follow-ups are due.
---

# LinkedIn network

You draft. The user sends. Nothing here opens LinkedIn, sends a message or connects to anyone. Show every draft in full before the user copies it, and never draft a message to someone the user has not named or picked from a list you showed them.

Output in the user's language, or the recipient's if the user says the recipient reads another one. Default: `cv.language` from the tracker's `profile.json`, else the language the user writes in.

Tool: `python skills/linkedin/li.py network ...`. Contacts live in `linkedin/network.json` under the Pentarch home.

## Steps

1. **Start with what is due.** Run `li.py network due`. Anything listed comes first: draft its follow-up before any new outreach. Done when every due row has a draft or a reason to drop it.
2. **Pick targets from the job search, not from the feed.** Read the tracker's `applications.json` and `scan.json` from its `data_dir` (default `data/`). Targets, in this order: companies with an application in stage `sent` or `process`; companies in `scan.json` `new` with score 4 or 5; companies in stage `watching`. Done when you have shown the user a list of at most 10 companies with the reason each is there.
3. **Two people per company.** Ask the user to look up, in their own browser, one recruiter or hiring manager and one engineer or peer in the team, and paste the names and roles. Done when each company in the list has at least one named person from the user.
4. **Warm before you ask.** For a person the user has never talked to, the first draft is a comment on one of their posts or the company's post, 25 to 40 words, adding one specific thing (a number, a question about a detail, a related experience). Never "Great post!". Done when the comment names a detail from the post.
5. **Connection note**, 300 characters. [fact: LinkedIn Help, "Personalize your invitation"] Who you are in half a line, the specific reason (their post, the role, a shared thing), no ask. Done when it is under 300 characters and has no ask.
6. **Recruiter or hiring manager message**, only after a connection is accepted or if the user already knows them. Shape: one line of context (the application id or role), one line of proof (a number or a link to the one project that matches the role), one question that is easy to answer. Under 100 words. Done when the message has exactly one question.
7. **Log it.** `li.py network add --name "<name>" --company <company> --why "<role, reason>" --days 7`. After every real contact: `li.py network touch <id> --days 14 --note "<what happened>"`. Done when every person in the reply has an id.

## Follow-up cadence

| situation | next touch |
|---|---|
| comment left, no reply | 7 days, then one more comment, then drop to 30 days |
| connection request sent | 7 days; if accepted, send the message within 2 days |
| message sent, no reply | 10 days, one gentle follow-up, then 30 days |
| application in `process` | after each interview, a thank-you within 24 hours, then nothing until they write |
| application `closed` | 60 days, one note with something you built since |

All cadences are conventions, unverified. Change `--days` when the user knows the person's rhythm.

## Weekly engagement

10 interactions a week: 5 comments on posts from people at target companies, 3 on peers in the same field, 2 on people who hire for the role. [convention, from public playbooks, unverified] Log only the ones that start a thread.

## What goes wrong

- Mass messages. One template sent to five recruiters reads as spam and gets the user flagged. Every draft names one specific thing about that person or company.
- Asking in the first message. A referral request to a stranger is a no; a question about the team is a maybe.
- Messaging before the application exists. If the company is in `scan.json` but not in `applications.json`, the message is about their work, never about a job.
- Writing to people the user did not pick. If the user says "find me recruiters", answer that you cannot browse LinkedIn and ask them to paste names.

## Job-search tie-in

When an application moves to `process` in the tracker, remind the user to add the interviewer to the network log after the interview. When one moves to `closed`, set a 60-day follow-up on every contact at that company instead of deleting them.
