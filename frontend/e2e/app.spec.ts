import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

async function expectAccessible(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes[0]?.target.join(" ")}`)).toEqual([]);
}

async function say(page: Page, text: string) {
  const box = page.getByLabel("Your message");
  await expect(box).toBeEnabled();
  await box.fill(text);
  await box.press("Enter");
}

test("landing page is accessible and leads into a check", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Find your next step");
  await expectAccessible(page);
  await page.getByRole("link", { name: /Stomach pain/ }).click();
  await expect(page.getByLabel("Your message")).toHaveValue(/stomach pain since/);
});

test("conversation gathers information and ends with a recommendation", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.getByText("What's been bothering you?")).toBeVisible();

  await say(page, "I've had stomach pain since yesterday.");
  await expect(page.getByText("How severe is it on a scale from 1 to 10?")).toBeVisible();
  await say(page, "About 5.");
  await expect(page.getByText("Is it constant, or does it come and go?")).toBeVisible();
  await expectAccessible(page);
  await say(page, "It comes and goes");
  await expect(page.getByText(/anything else along with it/)).toBeVisible();
  await say(page, "some nausea");

  await expect(page.getByRole("heading", { name: /Gastroenterology/ })).toBeVisible();
  await expect(page.getByText("A suggestion, not a diagnosis.")).toBeVisible();
  await expect(page.getByLabel("Your message")).toHaveCount(0);
  await expectAccessible(page);

  // A refresh resumes the same conversation (GET only: no model call).
  await page.reload();
  await expect(page.getByRole("heading", { name: /Gastroenterology/ })).toBeVisible();
});

test("emergency warning signs show the emergency banner immediately", async ({ page }) => {
  await page.goto("/chat");
  await say(page, "I have crushing chest pain going down my left arm");
  await expect(page.getByRole("alert").filter({ hasText: "This could be a medical emergency" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Emergency care/ })).toBeVisible();
});

test("decision trace shows one Jev call, built from stored data", async ({ page }) => {
  await page.goto("/chat");
  for (const [text, next] of [
    ["I've had stomach pain since yesterday.", "How severe"],
    ["About 5.", "come and go"],
    ["It comes and goes", "anything else"],
  ] as const) {
    await say(page, text);
    await expect(page.getByText(new RegExp(next)).last()).toBeVisible();
  }
  await say(page, "some nausea");
  await expect(page.getByRole("heading", { name: /Gastroenterology/ })).toBeVisible();

  const id = await page.evaluate(() => sessionStorage.getItem("carewise.conversationId"));
  await page.goto(`/trace/${id}`);
  await expect(page.getByRole("heading", { name: "Decision Trace" })).toBeVisible();
  await expect(page.getByText("Jev calls").locator("..")).toContainText("1");
  await expect(page.getByText("JEV_DECISION_COMPLETED")).toBeVisible();
  await expectAccessible(page);
});
