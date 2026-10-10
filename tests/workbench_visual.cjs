const { chromium, expect } = require("playwright/test");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");

async function main() {
  const output = path.join(os.tmpdir(), "customer-service-workbench-design");
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(() => localStorage.setItem("customer_service_session_id", "design-preview-session"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const now = "2026-10-10 14:30:00";
  let messages = [
    { id: 1, role: "assistant", content: "您好，我是小想。请问有什么可以帮您？", created_at: now },
    { id: 2, role: "user", content: "DD10001 物流到哪了？", created_at: now },
    { id: 3, role: "assistant", content: "您好，查询到订单 **DD10001**（蓝牙耳机 Pro）的物流信息：\n\n- **物流公司**：顺丰速运\n- **运单号**：SF123456789\n- **当前状态**：运输中\n- **最新位置**：上海转运中心\n- **预计送达**：明天\n\n请保持电话畅通，留意快递配送通知。", created_at: now },
    { id: 4, role: "user", content: "可以申请电子发票吗？", created_at: now },
    { id: 5, role: "assistant", content: "可以。订单完成后可以申请电子发票，抬头可选择个人或企业。\n\n企业发票需要提供**企业名称和纳税人识别号**。开票时限请以订单页面和平台政策为准。", created_at: now },
  ];
  const baseSession = { session_id: "design-preview-session", customer_name: "张同学", service_mode: "ai", assigned_agent: null, handoff_version: 0 };
  const queue = [
    { ...baseSession, session_id: "waiting-session-001", customer_name: "李同学", service_mode: "waiting_human", waiting_since: now, last_message: "耳机左耳没有声音，想咨询售后处理。", handoff_version: 1 },
    { ...baseSession, session_id: "receiving-session-002", customer_name: "王同学", service_mode: "human", assigned_agent: "人工客服A", waiting_since: now, last_message: "好的，我稍后补充故障视频。", handoff_version: 1 },
  ];
  const review = { review_no: "HRDEMO10001", session_id: baseSession.session_id, order_no: "DD10001", user_message: "耳机左耳没有声音，我想申请退款。", review_reason: "用户问题涉及质量争议，需要人工审核", review_status: "pending" };
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    let data;
    if (pathname.startsWith("/sessions/")) {
      const id = decodeURIComponent(pathname.slice("/sessions/".length));
      data = { session: queue.find((s) => s.session_id === id) || baseSession, messages };
    } else if (pathname === "/system/check") data = {
      postgres: { success: true, message: "PostgreSQL 连接正常" },
      milvus: { success: true, message: "Milvus 连接正常，知识库集合可用" },
      deepseek: { success: true, message: "DeepSeek 模型配置正常" },
      embedding: { success: true, message: "Embedding 配置正常" },
    };
    else if (pathname === "/handoffs") data = queue;
    else if (pathname === "/reviews/pending") data = [review];
    else if (pathname === "/traces/recent") data = [{
      id: 102, intent: "logistics_query", final_action: "auto_reply", user_message: "DD10001物流到哪了", created_at: now,
      trace_steps: [
        { node: "start", session_id: baseSession.session_id, message_saved: true },
        { node: "parse_message", intent: "logistics_query", order_no: "DD10001", confidence: 0.9 },
        { node: "query_order", tool: "order_tool", success: true, message: "订单查询成功" },
        { node: "query_logistics", tool: "logistics_tool", success: true, message: "物流查询成功" },
        { node: "generate_reply", final_action: "auto_reply" },
      ],
    }];
    else if (pathname === "/knowledge/files") data = ["after_sale_policy", "refund_policy", "logistics_policy", "invoice_policy", "quality_issue_policy"].map((name) => ({ file_name: `${name}.txt`, path: `data/knowledge/${name}.txt`, size: 1240 }));
    else if (pathname === "/knowledge/search") data = [{ source: "invoice_policy.txt", score: 0.782, text: "**电子发票申请**\n\n订单完成后可以申请电子发票，发票抬头可选择个人或企业。企业发票需填写企业名称和纳税人识别号。" }];
    else throw new Error(`Unexpected API request: ${pathname}`);
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ success: true, data }) });
  });
  try {
    await page.goto("http://127.0.0.1:5173/");
    await expect(page.locator(".message-content strong").first()).toBeVisible();
    await expect(page.locator(".chat-panel .message-list")).not.toContainText("**物流公司**");
    const views = [["chat", "客服对话"], ["support", "人工接待"], ["reviews", "人工审核"], ["traces", "执行轨迹"], ["knowledge", "知识库"], ["system", "系统状态"]];
    for (const width of [1440, 1024, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      for (const [key, label] of views) {
        await page.getByRole("button", { name: label, exact: true }).click();
        if (key === "support") {
          await page.getByRole("tab", { name: "等待 1" }).click();
          await expect(page.locator(".support-row")).toHaveCount(1);
          await page.locator(".support-row").click();
          await expect(page.getByRole("button", { name: "接入会话", exact: true })).toBeVisible();
        }
        if (key === "knowledge") {
          await page.getByRole("button", { name: "检索", exact: true }).click();
          await expect(page.locator(".score-label")).toHaveText("0.782");
        }
        if (key === "reviews") await expect(page.locator(".review-row")).toHaveCount(1);
        if (key === "traces") await expect(page.locator(".step")).toHaveCount(5);
        if (key === "system") await expect(page.locator(".status-card")).toHaveCount(4);
        await page.screenshot({ path: path.join(output, `${key}-${width}.png`), fullPage: true });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
      }
    }
    await page.getByRole("button", { name: "客服对话", exact: true }).click();
    await page.getByRole("button", { name: "查看会话", exact: true }).click();
    await expect(page.locator(".session-inspector")).toBeVisible();
    await page.getByRole("button", { name: "关闭会话详情", exact: true }).click();
    await expect(page.locator(".session-inspector")).not.toBeVisible();
    messages = [{ id: 91, role: "assistant", content: '<img src="invalid" onerror="window.__unsafe=true"><a href="javascript:window.__unsafe=true">unsafe link</a> **安全格式**', created_at: now }];
    await page.reload();
    await expect(page.locator(".message-content strong")).toHaveText("安全格式");
    expect(await page.locator(".message-content [onerror]").count()).toBe(0);
    expect(await page.locator('.message-content a[href^="javascript:"]').count()).toBe(0);
    expect(await page.evaluate(() => window.__unsafe)).toBeUndefined();
    expect(errors).toEqual([]);
    console.log(JSON.stringify({ result: "passed", output, screenshots: 18, checks: ["all-six-views", "desktop-tablet-mobile", "markdown-formatting", "html-sanitization", "support-filters", "mobile-inspector"] }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
