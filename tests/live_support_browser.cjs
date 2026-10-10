const { chromium, expect } = require("playwright/test");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

async function main() {
  const base = process.env.SUPPORT_UI_URL || "http://127.0.0.1:5173";
  const api = process.env.SUPPORT_API_URL || "http://127.0.0.1:8000";
  const sessionId = `support-ui-test-${Date.now()}`;
  const agentName = "UI验证客服";
  const artifacts = process.env.SUPPORT_SCREENSHOT_DIR || path.join(os.tmpdir(), "customer-service-live-support");
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const customerContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const staffContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await customerContext.addInitScript((id) => localStorage.setItem("customer_service_session_id", id), sessionId);
  const customer = await customerContext.newPage();
  const staff = await staffContext.newPage();
  const pageErrors = [];
  for (const page of [customer, staff]) {
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.route("**/system/check", (route) => route.fulfill({
      contentType: "application/json", body: JSON.stringify({ success: true, data: {} }),
    }));
  }
  try {
    await customer.goto(base);
    await customer.getByRole("button", { name: "转人工", exact: true }).click();
    await expect(customer.locator(".chat-panel .service-badge")).toHaveText("等待人工接入");
    await customer.locator(".composer input").fill("人工接管测试：耳机左耳没有声音");
    await customer.locator(".composer button").click();
    await expect(customer.locator(".message.user").last()).toContainText("人工接管测试");

    await staff.goto(base);
    await staff.getByRole("button", { name: /人工接待/ }).click();
    await staff.getByLabel("接待客服").fill(agentName);
    await staff.locator(".support-row").filter({ hasText: sessionId }).click();
    await staff.getByRole("button", { name: "接入会话", exact: true }).click();
    await expect(customer.locator(".chat-panel .service-badge")).toContainText(agentName, { timeout: 10000 });
    await staff.getByLabel("人工回复").fill("您好，我是人工客服，请提供故障视频。");
    await staff.locator(".support-conversation .composer button").click();
    await expect(customer.locator(".message.human").last()).toContainText("请提供故障视频", { timeout: 10000 });
    await customer.locator(".composer input").fill("收到，我正在准备视频。");
    await customer.locator(".composer button").click();
    await expect(staff.locator(".support-conversation .message.user").last()).toContainText("正在准备视频", { timeout: 10000 });
    await customer.reload();
    await expect(customer.locator(".message.human").last()).toContainText("请提供故障视频");
    await expect(customer.locator(".chat-panel .service-badge")).toContainText(agentName);

    for (const [page, name] of [[customer, "customer-desktop"], [staff, "staff-desktop"]]) {
      await page.screenshot({ path: path.join(artifacts, `${name}.png`), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    }
    await customer.setViewportSize({ width: 390, height: 844 });
    await staff.setViewportSize({ width: 390, height: 844 });
    for (const [page, name] of [[customer, "customer-mobile"], [staff, "staff-mobile"]]) {
      await page.screenshot({ path: path.join(artifacts, `${name}.png`), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    }
    await staff.getByRole("button", { name: "结束接待，交回 AI", exact: true }).click();
    await expect(customer.locator(".chat-panel .service-badge")).toHaveText("AI 服务中", { timeout: 10000 });
    expect(pageErrors).toEqual([]);
    console.log(JSON.stringify({ result: "passed", sessionId, artifacts,
      checks: ["customer-to-staff", "staff-to-customer", "page-reload", "desktop-mobile-layout", "release-to-ai"] }));
  } finally {
    // Leave this generated demonstration session out of the active queue, including on failure.
    const response = await fetch(`${api}/sessions/${sessionId}`).catch(() => null);
    const detail = response?.ok ? await response.json() : null;
    let session = detail?.data?.session;
    if (session?.service_mode === "waiting_human") {
      const claimed = await fetch(`${api}/handoffs/${sessionId}/claim`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ agent_name: agentName }),
      });
      session = (await claimed.json()).data;
    }
    if (session?.service_mode === "human" && session.assigned_agent === agentName) {
      await fetch(`${api}/handoffs/${sessionId}/release`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_name: agentName, handoff_version: session.handoff_version }),
      });
    }
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
