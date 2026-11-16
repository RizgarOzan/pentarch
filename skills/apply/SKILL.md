---
name: apply
description: Fill a job application form from the applicant profile, check every typed value against the profile, show the owner and send only after their explicit yes. Use when the user says to apply to a posting or a drafted application ("apply to X", "X'e başvur", "send the Acme one").
---

# Apply

You fill the form. The owner decides. Nothing is submitted without their yes in this chat, given after they saw the filled form.

Tools, stdlib only:

```
python -I tracker/apply.py list --stage drafted          # what is waiting, with ids
python -I tracker/apply.py check form.json --id ID       # FAIL lines and exit 1 on a wrong fact; on pass the record waits for approval
python -I tracker/apply.py approve ID --quote "..."      # the owner's own words, copied as they wrote them
python -I tracker/apply.py sent ID                       # refuses unless the last check passed and approval came after it
python -I skills/cv/cv.py check cv.md --jd posting.txt   # the CV rules, if the CV changed
```

Facts come from the `applicant` block of `tracker/profile.json` and the CV and letter in the record's `cv` and `package` paths (relative to `tracker/out/`). Nothing else is a source.

## Steps

1. Find the record (`apply.py list`). If there is none, add one with `apply.py add --company ... --role ... --posting URL --stage ready`.
2. Read the applicant block, the CV and the letter. If the CV still has `[number?]` or another gap, ask the owner for the fact first; never fill a gap yourself.
3. Open the posting's apply page in the browser. Fill every field from the applicant block, CV and letter. A required field the profile does not answer: stop and ask, don't guess. Upload the CV file the owner named (`cv_path`) or the PDF they made from the draft; if there is no PDF, ask.
4. Stop and hand over to the owner when the page asks to create an account, type a password, solve a CAPTCHA, pay, or accept terms beyond the application itself. Those are theirs.
5. Do not press submit. Read back every filled field as it now stands on the page into `form.json` as `{"label": "value"}`, using the page's own labels. Run `apply.py check form.json --id ID`. Fix every FAIL on the page, read back again, check again until it passes.
6. Show the owner: the company and role, each field and value (one line each), the file you attached, a screenshot if you can send one, and the exact button you will press ("I'll press Submit application"). Then ask and wait. Silence, "looks fine?" from you, or an approval of another application is not a yes.
7. On a clear yes for this application: `apply.py approve ID --quote "<their words>"`, press that one button once, and confirm the confirmation page or mail. Then `apply.py sent ID`. If the page shows an error instead, say so; don't press again without asking.
8. On no or "wait": leave the form unsent, `apply.py set ID ready --status "<what they said>"`.

A form changed after the check (a new field appeared, the owner asked for an edit) goes back to step 5: check again and ask again.
