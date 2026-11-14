import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const REVIEWER = { email: process.env.REVIEWER_EMAIL || "reviewer@gigbid.app", password: process.env.REVIEWER_PASSWORD || "review-local-only" };
export const API = process.env.API_URL || "http://localhost:8000";
export const GIGSIM = process.env.GIGSIM_URL || "http://localhost:8081";

export async function login(page: Page, who = REVIEWER) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password").fill(who.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).last().click();
  await page.waitForURL(/\/(inbox|onboarding)/);
}

/** Wait until at least one proposal is waiting for approval (scouting + analysis run in the background). */
export async function waitForPendingApproval(page: Page, request: APIRequestContext, minimum = 1): Promise<{ thread_id: string; job_id: string }[]> {
  const cookies = await page.context().cookies();
  const cookie = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  await request.post(`${API}/api/scout`, { headers: { cookie } });
  let pending: { thread_id: string; job_id: string }[] = [];
  await expect(async () => {
    const r = await request.get(`${API}/api/approvals`, { headers: { cookie } });
    pending = (await r.json()) as { thread_id: string; job_id: string }[];
    expect(pending.length).toBeGreaterThanOrEqual(minimum);
  }).toPass({ timeout: 110_000, intervals: [3_000] });
  return pending;
}
