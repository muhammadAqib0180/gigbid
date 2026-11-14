import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("mobile: inbox renders without horizontal page scroll and the nav is reachable", async ({ page }) => {
  await login(page);
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.getByRole("link", { name: "Pipeline" }).click();
  await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
});
