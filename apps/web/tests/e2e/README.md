Playwright specs (run against a live stack on the deterministic `test` model profile):

1. `gigbid.spec.ts` - onboarding, approve a proposal (evidence hover + dry-run preview), reject with a reason,
   edit a draft (Compliance strips an injected WhatsApp number on re-check), degraded-mode banner (GigSim outage switch).
2. `mobile.spec.ts` - Pixel 7 viewport: inbox without horizontal page scroll, navigation reachable.

```
python -m scripts.dev --reset --web      # terminal 1
cd apps/web && npx playwright install chromium && npm run test:e2e   # terminal 2
```
The HTML report is written to `apps/web/playwright-report/`.
