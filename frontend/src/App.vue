<script setup>
import { computed, onMounted, ref } from "vue";
import {
  approveReview,
  chat,
  getKnowledgeFiles,
  getPendingReviews,
  getRecentTraces,
  getSessionDetail,
  rejectReview,
  reindexKnowledge,
  searchKnowledge,
  systemCheck,
} from "./api";

const activeView = ref("chat");
const loading = ref(false);
const notice = ref("");
const error = ref("");

const sessionId = ref(localStorage.getItem("customer_service_session_id") || "");
const inputMessage = ref("DD10001物流到哪了");
const messages = ref([
  {
    role: "assistant",
    content: "您好，我是小想。可以查询订单、物流、退款售后，也可以回答企业政策问题。",
  },
]);

const systemStatus = ref(null);
const reviews = ref([]);
const selectedReview = ref(null);
const reviewerName = ref("人工客服A");
const reviewerReply = ref("已核实用户反馈，请上传商品故障视频，我们会继续处理退款申请。");
const sessionDetail = ref(null);
const traces = ref([]);
const selectedTrace = ref(null);
const knowledgeFiles = ref([]);
const knowledgeQuery = ref("耳机左耳没声音可以退款吗");
const knowledgeResults = ref([]);

const navItems = [
  { id: "chat", label: "客服对话", hint: "Agent 调试" },
  { id: "reviews", label: "人工审核", hint: "待处理工单" },
  { id: "traces", label: "执行轨迹", hint: "节点与工具" },
  { id: "knowledge", label: "知识库", hint: "RAG 管理" },
  { id: "system", label: "系统状态", hint: "服务自检" },
];

const currentTitle = computed(() => {
  return navItems.find((item) => item.id === activeView.value)?.label || "工作台";
});

function setNotice(message) {
  notice.value = message;
  error.value = "";
}

function setError(message) {
  error.value = message;
  notice.value = "";
}

async function runAction(action, successMessage) {
  loading.value = true;
  try {
    const result = await action();
    if (successMessage) {
      setNotice(successMessage);
    }
    return result;
  } catch (err) {
    setError(err.message || "操作失败");
    return null;
  } finally {
    loading.value = false;
  }
}

async function sendMessage() {
  const content = inputMessage.value.trim();
  if (!content) {
    setError("请输入用户问题");
    return;
  }

  messages.value.push({ role: "user", content });
  inputMessage.value = "";

  const result = await runAction(() => chat(content, sessionId.value), "");
  if (!result?.success) {
    messages.value.push({ role: "assistant", content: result?.message || "回复生成失败" });
    return;
  }

  sessionId.value = result.data.session_id;
  localStorage.setItem("customer_service_session_id", sessionId.value);
  messages.value.push({ role: "assistant", content: result.data.reply });
  await refreshTraces(false);
}

async function refreshSystem(showMessage = true) {
  const result = await runAction(() => systemCheck(), showMessage ? "系统自检已完成" : "");
  if (result) {
    systemStatus.value = result.data;
  }
}

async function refreshReviews(showMessage = true) {
  const result = await runAction(() => getPendingReviews(), showMessage ? "待审核列表已刷新" : "");
  if (result) {
    reviews.value = result.data || [];
    selectedReview.value = reviews.value[0] || null;
  }
}

async function handleReview(action) {
  if (!selectedReview.value) {
    setError("请选择审核单");
    return;
  }

  const payload = {
    review_no: selectedReview.value.review_no,
    reviewer_name: reviewerName.value,
    reviewer_reply: reviewerReply.value,
  };

  const result = await runAction(
    () => (action === "approve" ? approveReview(payload) : rejectReview(payload)),
    action === "approve" ? "审核单已处理完成" : "审核单已驳回",
  );

  if (result?.success) {
    await refreshReviews(false);
    if (selectedReview.value?.session_id) {
      await loadSession(selectedReview.value.session_id);
    }
  }
}

async function loadSession(targetSessionId = sessionId.value) {
  if (!targetSessionId) {
    setError("暂无会话 ID");
    return;
  }

  const result = await runAction(() => getSessionDetail(targetSessionId), "会话详情已加载");
  if (result?.success) {
    sessionDetail.value = result.data;
  }
}

async function refreshTraces(showMessage = true) {
  const result = await runAction(() => getRecentTraces(), showMessage ? "执行轨迹已刷新" : "");
  if (result) {
    traces.value = result.data || [];
    selectedTrace.value = traces.value[0] || null;
  }
}

async function refreshKnowledge(showMessage = true) {
  const result = await runAction(() => getKnowledgeFiles(), showMessage ? "知识库文件已刷新" : "");
  if (result) {
    knowledgeFiles.value = result.data || [];
  }
}

async function doKnowledgeSearch() {
  const query = knowledgeQuery.value.trim();
  if (!query) {
    setError("请输入检索问题");
    return;
  }

  const result = await runAction(() => searchKnowledge(query), "知识库检索已完成");
  if (result?.success) {
    knowledgeResults.value = result.data || [];
  }
}

async function doReindex() {
  await runAction(() => reindexKnowledge(), "知识库重建完成");
  await refreshKnowledge(false);
}

function formatStepName(step) {
  return step.node || step.tool || "step";
}

function switchView(view) {
  activeView.value = view;
  notice.value = "";
  error.value = "";

  if (view === "system") refreshSystem(false);
  if (view === "reviews") refreshReviews(false);
  if (view === "traces") refreshTraces(false);
  if (view === "knowledge") refreshKnowledge(false);
}

onMounted(async () => {
  await refreshSystem(false);
  await refreshReviews(false);
  await refreshTraces(false);
  await refreshKnowledge(false);
});
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">想</div>
        <div>
          <h1>小想客服 Agent</h1>
          <p>企业后端工作台</p>
        </div>
      </div>

      <nav class="nav-list" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.id"
          class="nav-item"
          :class="{ active: activeView === item.id }"
          type="button"
          @click="switchView(item.id)"
        >
          <span>{{ item.label }}</span>
          <small>{{ item.hint }}</small>
        </button>
      </nav>

      <div class="sidebar-card">
        <span class="status-dot" :class="{ ok: systemStatus?.postgres?.success }"></span>
        <div>
          <strong>后端 API</strong>
          <p>http://127.0.0.1:8000</p>
        </div>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Customer Service Agent</p>
          <h2>{{ currentTitle }}</h2>
        </div>
        <div class="session-pill">
          {{ sessionId || "新会话" }}
        </div>
      </header>

      <div v-if="notice" class="notice success">{{ notice }}</div>
      <div v-if="error" class="notice error">{{ error }}</div>

      <section v-if="activeView === 'chat'" class="view-grid chat-grid">
        <div class="panel chat-panel">
          <div class="panel-header">
            <div>
              <h3>客服对话</h3>
              <p>测试聊天、上下文记忆、RAG 和人工审核分流。</p>
            </div>
            <button class="ghost-button" type="button" @click="loadSession()">查看会话</button>
          </div>

          <div class="message-list">
            <div
              v-for="(message, index) in messages"
              :key="`${message.role}-${index}`"
              class="message"
              :class="message.role"
            >
              <span>{{ message.role }}</span>
              <p>{{ message.content }}</p>
            </div>
          </div>

          <form class="composer" @submit.prevent="sendMessage">
            <input v-model="inputMessage" type="text" placeholder="输入：DD10001物流到哪了" />
            <button type="submit" :disabled="loading">发送</button>
          </form>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>会话详情</h3>
              <p>人工回复写回后会在这里出现。</p>
            </div>
          </div>
          <div v-if="sessionDetail" class="compact-list">
            <div v-for="message in sessionDetail.messages" :key="message.id" class="compact-item">
              <strong>{{ message.role }}</strong>
              <p>{{ message.content }}</p>
            </div>
          </div>
          <div v-else class="empty">暂无会话详情</div>
        </div>
      </section>

      <section v-if="activeView === 'reviews'" class="view-grid review-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>待审核工单</h3>
              <p>处理质量争议、投诉、退款风险问题。</p>
            </div>
            <button class="ghost-button" type="button" @click="refreshReviews()">刷新</button>
          </div>

          <div class="compact-list">
            <button
              v-for="review in reviews"
              :key="review.review_no"
              class="review-row"
              :class="{ selected: selectedReview?.review_no === review.review_no }"
              type="button"
              @click="selectedReview = review"
            >
              <strong>{{ review.review_no }}</strong>
              <span>{{ review.order_no || "无订单" }}</span>
              <p>{{ review.review_reason }}</p>
            </button>
          </div>
          <div v-if="!reviews.length" class="empty">暂无待审核工单</div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>审核处理</h3>
              <p>审核结果会写回用户会话。</p>
            </div>
          </div>

          <template v-if="selectedReview">
            <div class="detail-block">
              <label>用户问题</label>
              <p>{{ selectedReview.user_message }}</p>
            </div>
            <div class="detail-block">
              <label>审核原因</label>
              <p>{{ selectedReview.review_reason }}</p>
            </div>
            <input v-model="reviewerName" class="field" type="text" />
            <textarea v-model="reviewerReply" class="field textarea"></textarea>
            <div class="button-row">
              <button type="button" @click="handleReview('approve')">处理完成</button>
              <button class="danger-button" type="button" @click="handleReview('reject')">驳回</button>
            </div>
          </template>
          <div v-else class="empty">请选择一个审核单</div>
        </div>
      </section>

      <section v-if="activeView === 'traces'" class="view-grid trace-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>最近执行轨迹</h3>
              <p>查看每轮 Agent 的意图、工具和最终动作。</p>
            </div>
            <button class="ghost-button" type="button" @click="refreshTraces()">刷新</button>
          </div>

          <div class="compact-list">
            <button
              v-for="trace in traces"
              :key="trace.id"
              class="trace-row"
              :class="{ selected: selectedTrace?.id === trace.id }"
              type="button"
              @click="selectedTrace = trace"
            >
              <strong>#{{ trace.id }} {{ trace.intent }}</strong>
              <span>{{ trace.final_action }}</span>
              <p>{{ trace.user_message }}</p>
            </button>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>节点明细</h3>
              <p>展示 LangGraph 工作流经过的节点。</p>
            </div>
          </div>
          <div v-if="selectedTrace" class="steps">
            <div v-for="(step, index) in selectedTrace.trace_steps || []" :key="index" class="step">
              <span>{{ index + 1 }}</span>
              <div>
                <strong>{{ formatStepName(step) }}</strong>
                <pre>{{ JSON.stringify(step, null, 2) }}</pre>
              </div>
            </div>
          </div>
          <div v-else class="empty">暂无执行轨迹</div>
        </div>
      </section>

      <section v-if="activeView === 'knowledge'" class="view-grid knowledge-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>知识库文件</h3>
              <p>查看企业政策文件并触发重新入库。</p>
            </div>
            <button class="ghost-button" type="button" @click="refreshKnowledge()">刷新</button>
          </div>

          <div class="file-list">
            <div v-for="file in knowledgeFiles" :key="file.path" class="file-item">
              <strong>{{ file.file_name }}</strong>
              <span>{{ file.size }} bytes</span>
            </div>
          </div>
          <button class="wide-button" type="button" :disabled="loading" @click="doReindex">
            重新构建向量库
          </button>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>知识库检索</h3>
              <p>测试 Milvus 中的政策片段召回效果。</p>
            </div>
          </div>
          <form class="search-box" @submit.prevent="doKnowledgeSearch">
            <input v-model="knowledgeQuery" type="text" />
            <button type="submit">检索</button>
          </form>
          <div class="compact-list">
            <div v-for="(doc, index) in knowledgeResults" :key="index" class="compact-item">
              <strong>{{ doc.source }} · {{ doc.score }}</strong>
              <p>{{ doc.text }}</p>
            </div>
          </div>
        </div>
      </section>

      <section v-if="activeView === 'system'" class="view-grid system-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>系统自检</h3>
              <p>检查 PostgreSQL、Milvus、DeepSeek 和 Embedding 配置。</p>
            </div>
            <button class="ghost-button" type="button" @click="refreshSystem()">重新检查</button>
          </div>

          <div v-if="systemStatus" class="status-grid">
            <div v-for="(item, key) in systemStatus" :key="key" class="status-card">
              <span class="status-dot" :class="{ ok: item.success }"></span>
              <strong>{{ key }}</strong>
              <p>{{ item.message }}</p>
            </div>
          </div>
          <div v-else class="empty">暂无系统状态</div>
        </div>
      </section>
    </main>
  </div>
</template>
