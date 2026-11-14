# 3-minute demo video script

Record at 1280x720 with OBS; local stack `python -m scripts.dev --reset --web` (or the live URL). Voice-over in brackets.

| Time | Screen | Say / do |
|---|---|---|
| 0:00-0:15 | Login -> Inbox | "GigBid is a team of agents that finds freelance jobs, checks them and drafts proposals - and never sends anything without me." Point at fit bars, risk badges, actions, Connects cost. |
| 0:15-0:40 | Inbox filter "Risky" -> a scam job -> Job detail | **Scam caught:** risk badge "Scam", flags (off_platform_payment, unpaid_work, payment_unverified), decision SKIP with reason. "Rules give a floor that injected text cannot argue away." |
| 0:40-1:00 | A job tagged injection -> Job detail | **Injection ignored:** yellow banner "Prompt injection detected and ignored", the planted text shown as untrusted; open the draft: no WhatsApp number, no 'I am an AI bot'. |
| 1:00-1:50 | Inbox "Needs approval" -> Proposal studio | **Inbox to approved proposal:** hover two claims (green = supported, shows the case study it came from), Critic + Compliance badges, dry-run preview (Connects, balance after). Click Edit, cut the first sentence, Save -> re-checked; Approve. Job detail shows `submitted`. |
| 1:50-2:10 | Agent run viewer | Live node timeline (analyst/risk/matcher in parallel), checkpoint history with Replay, link to the LangSmith trace. |
| 2:10-2:45 | Pipeline -> Messages | **Client reply handled:** card moved to "replied"; Messages shows the client's "are you free for a call?" and the suggested reply with interview slots; Approve -> card moves to "interview". |
| 2:45-3:00 | Settings | Memory viewer (style candidates from edits, promotion rule), autonomy "never auto-send". Close: "Every number in the README comes from evals/results." |

Tip: `curl -X POST -H "X-Admin-Token: gigsim-admin-token" localhost:8081/admin/tick?minutes=90` makes simulated clients reply immediately.
