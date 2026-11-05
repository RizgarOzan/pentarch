---
name: linkedin-profile
description: Audit and rewrite a LinkedIn profile (headline, About, experience bullets, featured, skills) against a 100-point rubric and the user's target roles. Use when the user asks to improve their LinkedIn profile, headline or About, or asks why recruiters do not reach out.
---

# LinkedIn profile

You produce the text and the score. The user pastes it into LinkedIn. Nothing here opens LinkedIn.

Output in the user's language: `cv.language` in the tracker's `profile.json` if present, otherwise the language they write in. If the user targets roles in another country, write the profile in that market's language and say so.

Tool: `python skills/linkedin/li.py profile export.json`.

## Steps

1. **Export by hand.** Ask the user to copy their profile into a JSON file with these keys. Missing keys count as empty.

   ```json
   {"headline": "", "about": "", "featured": 0, "banner": false, "photo_px": 0,
    "experience": [{"title": "", "bullets": [""]}], "skills": [""], "pinned_skills": [""],
    "recommendations": 0, "posts_30d": 0, "comments_30d": 0, "custom_url": false, "contact": ""}
   ```

   Done when the file parses and the user confirms the current role is first in `experience`.
2. **Score.** Run `python skills/linkedin/li.py profile export.json`. It prints each rubric row, the total, and the three rows that lose the most points. Done when the total is in your reply.
3. **Know the target.** Read `target_roles`, `skills` and `locations` from the tracker's `profile.json` if it exists; otherwise ask for the one role title the user wants to be found for. Done when you can name the three search terms a recruiter for that role would type.
4. **Rewrite, biggest loss first.** For each of the three rows, write the new text, then show old and new side by side. Rules per field are below. Done when each rewrite is checked against the field rule and the user's voice (see `linkedin-post` step 1 for how to get the voice).
5. **Re-score.** Ask the user to update the JSON after they paste the changes, run `python skills/linkedin/li.py profile` again, and compare. Done when the new total is in the reply with the delta.
6. **Schedule the rest.** Rows that need the user's action and not text (photo, banner, recommendations, activity) go into a short list with a date each. Recommendations: draft the request message for them, one per person, naming the specific thing to mention.

## Field rules

- **Headline**, 220 characters. [fact: LinkedIn Help, "Edit your headline"] Shape: what you do | who it helps | one result or proof. Role title first, since search matches on it. A job title alone ("Student at X") scores 6 of 12.
- **About**, 2,600 characters. [fact: LinkedIn Help] The first 265 characters show before "see more" on desktop [convention, unverified]: put the hook there, a number or a question. Body 150 to 300 words, first person, one paragraph per idea, at least one number, ends with how to contact. Keywords from step 3 appear naturally at least once each.
- **Experience**: every entry has bullets; the current role has at least two that start with a verb and carry a number (shipped, cut, grew, built). "Responsible for" is a label, replace it with what happened.
- **Featured**: three items. A project link, a post that did well, a writing sample. A CV PDF counts as one.
- **Skills**: 20 or more listed, top 3 pinned to the target role. Pinned skills show without clicking.
- **Photo** 400 px or larger on the short side, **banner** 1584x396 [fact: LinkedIn Help, "Profile photo and background photo"]. Banner shows what the user works on, not a stock gradient.
- **Recommendations**: three. Ask people who saw the work, give them the two sentences you hope they write.
- **Activity**: 4 posts or 20 comments in the last 30 days. Recruiters see "Activity" before "Experience" on mobile [convention, unverified].
- **Contact**: custom URL and at least one channel (email or a site). Open-to-work badge is the user's call; mention that the "recruiters only" setting exists.

## Rubric

| row | points | full marks when |
|---|---|---|
| headline | 12 | present, 220 or fewer chars, has a separator or a number |
| about_open | 10 | first 265 chars exist and contain a number or a question |
| about_body | 10 | 150 to 300 words and at least one number |
| featured | 8 | 3 items |
| banner | 6 | custom banner |
| photo | 6 | 400 px or more |
| current_role | 10 | 2 bullets with a number |
| experience_depth | 8 | every entry has a bullet |
| skills | 6 | 20 listed and 3 pinned |
| recommendations | 8 | 3 |
| activity | 10 | 4 posts or 20 comments in 30 days |
| contact | 6 | custom URL and a channel |

Weights are a convention adapted from public profile checklists, unverified against LinkedIn's search ranking. Treat the score as a to-do order, not a prediction.

## Job-search tie-in

Applications in stage `sent` or `process` in `applications.json` (tracker `data_dir`): recruiters at those companies will open the profile. Check that the headline and the first 265 characters of About match the role applied for, and that the Featured section has the project most relevant to that company. Say which application you checked against.
