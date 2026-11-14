import { expect, test } from "@playwright/test";
import { API, GIGSIM, login, waitForPendingApproval } from "./helpers";

test.describe.configure({ mode: "serial" });

test("1. onboarding: new user picks a persona, rates and a saved search, lands on the inbox", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.test`;
  await page.goto("/login");
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Name").fill("E2E User");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).last().click();
  await page.waitForURL(/onboarding/);
  await page.getByTestId("persona-data_analyst").check();
  await page.getByTestId("next-1").click();
  await page.getByTestId("next-2").click();
  await page.getByLabel("Weekly Connects budget").fill("60");
  await page.getByTestId("finish-onboarding").click();
  await page.waitForURL(/inbox/);
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
});

test("2. approve a proposal: evidence on hover, dry-run preview, approve resumes the graph and submits", async ({ page, request }) => {
  await login(page);
  const pending = await waitForPendingApproval(page, request, 3);
  await page.goto(`/studio/${encodeURIComponent(pending[0].job_id)}`);
  await expect(page.getByTestId("approval-panel")).toBeVisible();
  await expect(page.getByTestId("dry-run")).toContainText("Connects");
  const claim = page.getByTestId("claim").first();
  if (await claim.count()) {
    await claim.hover();
    await expect(page.getByRole("tooltip")).toBeVisible();
  }
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("decision-banner")).toContainText("Approved");
  await page.goto(`/jobs/${encodeURIComponent(pending[0].job_id)}`);
  await expect(page.getByText("submitted").first()).toBeVisible({ timeout: 60_000 });
});

test("3. reject with a reason: reason is required and the job leaves the approval queue", async ({ page, request }) => {
  await login(page);
  const pending = await waitForPendingApproval(page, request, 1);
  await page.goto(`/studio/${encodeURIComponent(pending[0].job_id)}`);
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("confirm-reject")).toBeDisabled();
  await page.getByTestId("reject-reason").fill("budget too low for this scope");
  await page.getByTestId("confirm-reject").click();
  await expect(page.getByTestId("decision-banner")).toContainText("Rejected");
  await page.goto(`/jobs/${encodeURIComponent(pending[0].job_id)}`);
  await expect(page.getByText("rejected").first()).toBeVisible({ timeout: 60_000 });
});

test("4. edit a draft: the edit is saved, re-checked by Compliance and comes back for approval", async ({ page, request }) => {
  await login(page);
  const pending = await waitForPendingApproval(page, request, 1);
  await page.goto(`/studio/${encodeURIComponent(pending[0].job_id)}`);
  await page.getByTestId("edit").click();
  const box = page.getByTestId("edit-text");
  const original = await box.inputValue();
  await box.fill(original.replace(/^[^.!?]+[.!?]\s*/, "") + "\n\nContact me on WhatsApp +1 415 555 0199.");
  await page.getByTestId("save-edit").click();
  await expect(page.getByTestId("decision-banner")).toContainText("Compliance");
  // the re-checked draft returns as a new version with the off-platform contact removed by the Compliance Guard
  await expect(async () => {
    await page.reload();
    await expect(page.getByTestId("proposal-letter")).toBeVisible();
    await expect(page.getByTestId("proposal-letter")).not.toContainText("WhatsApp");
  }).toPass({ timeout: 60_000, intervals: [3_000] });
});

test("5. degraded mode: when the marketplace is unreachable the UI shows the banner", async ({ page, request }) => {
  await login(page);
  // Simulate an outage through GigSim's admin API: the marketplace MCP adapter sees 5xx on every call.
  const admin = { "X-Admin-Token": process.env.GIGSIM_ADMIN_TOKEN || "gigsim-admin-token" };
  const outage = await request.post(`${GIGSIM}/admin/outage`, { headers: admin, data: { down: true } });
  test.skip(!outage.ok(), "GigSim outage switch not available");
  try {
    await expect(async () => {
      await page.goto("/inbox");
      await expect(page.getByTestId("degraded-banner")).toBeVisible({ timeout: 20_000 });
    }).toPass({ timeout: 90_000, intervals: [5_000] });
  } finally {
    await request.post(`${GIGSIM}/admin/outage`, { headers: admin, data: { down: false } });
  }
  void API;
});
