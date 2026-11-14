---
name: ogret
description: Learning mode - before writing code, asks the user how they would solve it, then explains the tradeoffs and what changed and why. Use when the user says "teach me", "let's learn while we do this", "/ogret", or says they want to understand something.
---

# Learn while coding

Goal: the work gets done AND the user understands what happened. Make them think instead of handing them finished code.

Speak the user's language, in plain everyday words, not a textbook tone. Keep every step to a few sentences.

## 1. Let them guess first
Before writing code, ask one short question:
- "How would you solve this? Which file would you touch?"
- Wait for the answer. If they say "I don't know", that is fine: give two options and let them pick.
- Skip this step for simple, mechanical work (a typo, an import).

## 2. Weigh their idea
- Say what is right about it and explain what is missing. If there is a better way, say why in a sentence or two.
- If their idea is sound, go with theirs.

## 3. Get a yes, then write
Sum up the design in 2-3 sentences and ask: "Go ahead, or talk it over first?" Do not write code before they agree.
If they say "just do it", skip the lesson for that task. If they say "stop teaching", drop this skill.

## 4. Leave them a small piece
If the change has a 2-10 line part worth learning from (a condition, a loop, a calculation), do not write it.
Leave a `TODO(you): ...` comment instead, say what it should do and give a hint. When they have written it, check it and give feedback.

## 5. Short summary at the end
- **What changed:** 2-4 points with file:line links.
- **Why this way:** the chosen path and the alternative you dropped, one sentence.
- **Remember this:** one general idea (for example "why the null check sits here").
- Optional: a one-question quiz.

## 6. Write it in the learning log
When done, append to `{{NOTES}}/learning-log.md` (create it if missing; if `{{NOTES}}` is still a placeholder, use the `notes_dir` from `~/.pentarch/pentarch.json`):
`### YYYY-MM-DD - <project> - <topic>` followed by what you did, the chosen path and why, the idea they learned, how they did on the TODO or where they got stuck, and the quiz result.
