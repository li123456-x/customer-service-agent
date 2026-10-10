<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import LiveSupport from "./LiveSupport.vue";
import MessageContent from "./MessageContent.vue";
import { messagePreview } from "./messageFormat";
import {
  Activity, ArrowUpRight, BookOpen, Bot, Check, CheckCircle2, ClipboardCheck,
  Copy, Database, FileText, Headset, Info, MessageSquare, Plus, RefreshCw,
  Search, Send, Server, UserRound, Workflow, X,
} from "lucide-vue-next";
import {
  approveReview,
  chat,
  getKnowledgeFiles,
  getPendingReviews,
  getRecentTraces,
  getSessionDetail,
  rejectReview,
  requestHandoff,
  reindexKnowledge,
  searchKnowledge,
  systemCheck,
} from "./api";

const activeView = ref("chat");
const loading = ref(false);
const notice = ref("");
const error = ref("");

const sessionId = ref(localStorage.getItem("customer_service_session_id") || `session-${crypto.randomUUID()}`);
localStorage.setItem("customer_service_session_id", sessionId.value);
const inputMessage = ref("");
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
const messageList = ref(null);
const inspectorOpen = ref(false);
const sending = ref(false);
const lastCheckedAt = ref(null);
const currentOrder = computed(() => {
  for (const message of [...messages.value].reverse()) {
    if (message.role === "user") {
      const match = message.content.match(/DD\d+/i);
      if (match) return match[0].toUpperCase();
    }
  }
  return null;
});
const serviceEntries = computed(() => Object.entries(systemStatus.value || {}));
const healthyServices = computed(() => serviceEntries.value.filter(([, item]) => item.success).length);
const conversationMode = computed(() => sessionDetail.value?.session?.service_mode || "ai");
const conversationStatus = computed(() => ({
  ai: "AI 服务中", waiting_human: "等待人工接入", human: `人工客服 ${sessionDetail.value?.session?.assigned_agent || ""} 接待中`,
})[conversationMode.value]);
let conversationTimer;
let syncing = false;
let disposed = false;

const navItems = [
  { id: "chat", label: "客服对话", icon: MessageSquare, group: "接待中心" },
  { id: "support", label: "人工接待", icon: Headset, group: "接待中心" },
  { id: "reviews", label: "人工审核", icon: ClipboardCheck, group: "接待中心" },
  { id: "traces", label: "执行轨迹", icon: Workflow, group: "管理与监控" },
  { id: "knowledge", label: "知识库", icon: BookOpen, group: "管理与监控" },
  { id: "system", label: "系统状态", icon: Activity, group: "管理与监控" },
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
  if (loading.value) return;
  const content = inputMessage.value.trim();
  if (!content) {
    setError("请输入用户问题");
    return;
  }

  const pendingMessage = { id: `pending-${crypto.randomUUID()}`, role: "user", content };
  messages.value.push(pendingMessage);
  inputMessage.value = "";
  sending.value = true;
  await nextTick();
  messageList.value?.scrollTo({ top: messageList.value.scrollHeight });
  const result = await runAction(() => chat(content, sessionId.value), "");
  sending.value = false;
  if (!result?.success) {
    messages.value = messages.value.filter((message) => message.id !== pendingMessage.id);
    if (!inputMessage.value) inputMessage.value = content;
    setError(result?.message || error.value || "消息发送失败");
    return;
  }

  sessionId.value = result.data.session_id;
  localStorage.setItem("customer_service_session_id", sessionId.value);
  sessionDetail.value = { session: result.data.session, messages: sessionDetail.value?.messages || [] };
  await syncConversation();
}

async function syncConversation() {
  const target = sessionId.value;
  if (syncing || disposed) return;
  syncing = true;
  try {
    const result = await getSessionDetail(target);
    if (!disposed && sessionId.value === target && result.success) {
      const previousLast = messages.value.at(-1)?.id;
      sessionDetail.value = result.data;
      if (result.data.messages.length) messages.value = result.data.messages;
      if (previousLast !== messages.value.at(-1)?.id) {
        await nextTick();
        messageList.value?.scrollTo({ top: messageList.value.scrollHeight });
      }
    }
  } catch (err) {
    if (!disposed && sessionId.value === target) setError(err.message || "会话更新失败");
  } finally {
    syncing = false;
  }
}

async function transferToHuman() {
  if (loading.value) return;
  const result = await runAction(() => requestHandoff(sessionId.value), "");
  if (result?.success) {
    sessionDetail.value = { session: result.data, messages: sessionDetail.value?.messages || [] };
    await syncConversation();
  }
}

function newConversation() {
  if (loading.value) return;
  sessionId.value = `session-${crypto.randomUUID()}`;
  localStorage.setItem("customer_service_session_id", sessionId.value);
  sessionDetail.value = null;
  messages.value = [{ role: "assistant", content: "您好，请问有什么可以帮您？" }];
  error.value = "";
  notice.value = "";
  inputMessage.value = "";
}

function messageLabel(message) {
  return { user: "用户", assistant: "AI 客服", human: message.sender_name || "人工客服", system: "接待通知" }[message.role] || message.role;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function formatSize(size) {
  return Number(size) >= 1024 ? `${(Number(size) / 1024).toFixed(1)} KB` : `${size || 0} B`;
}

async function copySession() {
  try {
    await navigator.clipboard.writeText(sessionId.value);
    setNotice("会话编号已复制");
  } catch {
    setError("无法复制会话编号");
  }
}

async function openSession() {
  inspectorOpen.value = true;
  await loadSession();
}

async function refreshSystem(showMessage = true) {
  const result = await runAction(() => systemCheck(), showMessage ? "系统自检已完成" : "");
  if (result) {
    systemStatus.value = result.data;
    lastCheckedAt.value = new Date();
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

  const targetSessionId = selectedReview.value.session_id;
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
    if (targetSessionId === sessionId.value) {
      await syncConversation();
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
    if (targetSessionId === sessionId.value) {
      sessionDetail.value = result.data;
      if (result.data.messages.length) messages.value = result.data.messages;
    }
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
  conversationTimer = setInterval(() => {
    if (!document.hidden && activeView.value === "chat" && !loading.value) syncConversation();
  }, 1500);
  await syncConversation();
  await refreshSystem(false);
});
onUnmounted(() => { disposed = true; clearInterval(conversationTimer); });
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><Headset :size="21" :stroke-width="2" /></div>
        <div>
          <h1>小想客服</h1>
          <p>客服工作台</p>
        </div>
      </div>

      <nav class="nav-list" aria-label="主导航">
        <div v-for="group in ['接待中心', '管理与监控']" :key="group" class="nav-group">
          <p class="nav-group-label">{{ group }}</p>
          <button v-for="item in navItems.filter((item) => item.group === group)" :key="item.id"
            class="nav-item" :class="{ active: activeView === item.id }" :title="item.label"
            :aria-label="item.label" :aria-current="activeView === item.id ? 'page' : undefined"
            type="button" @click="switchView(item.id)">
            <component :is="item.icon" :size="18" :stroke-width="1.8" />
            <span>{{ item.label }}</span>
            <span v-if="item.id === 'reviews' && reviews.length" class="nav-count">{{ reviews.length }}</span>
          </button>
        </div>
      </nav>

      <button class="sidebar-card" type="button" @click="switchView('system')" title="查看服务状态">
        <span class="status-dot" :class="{ ok: systemStatus }"></span>
        <div>
          <strong>{{ systemStatus ? '服务已连接' : '服务待检查' }}</strong>
          <p>本地工作空间</p>
        </div>
        <ArrowUpRight :size="15" />
      </button>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">工作台 <span>/</span> {{ currentTitle }}</p>
          <h2>{{ currentTitle }}</h2>
        </div>
        <div class="topbar-actions">
          <span class="workspace-status"><span class="status-dot" :class="{ ok: systemStatus }"></span>本地环境</span>
          <button v-if="activeView === 'chat'" class="primary-button" type="button" :disabled="loading" @click="newConversation"><Plus :size="16" />新会话</button>
        </div>
      </header>

      <div v-if="notice" role="status" class="notice success"><CheckCircle2 :size="17" />{{ notice }}<button class="icon-button" title="关闭提示" aria-label="关闭提示" @click="notice = ''"><X :size="16" /></button></div>
      <div v-if="error" role="alert" class="notice error"><Info :size="17" />{{ error }}<button class="icon-button" title="关闭提示" aria-label="关闭提示" @click="error = ''"><X :size="16" /></button></div>

      <section v-if="activeView === 'chat'" class="view-grid chat-grid">
        <div class="panel chat-panel">
          <div class="panel-header">
            <div>
              <div class="conversation-heading"><div class="conversation-avatar"><Bot :size="20" /></div><div><h3>{{ sessionDetail?.session?.customer_name || '当前会话' }}</h3>
              <span class="service-badge" :class="conversationMode"><span class="badge-dot"></span>{{ conversationStatus }}</span></div></div>
            </div>
            <div class="button-row header-buttons">
              <button v-if="conversationMode === 'ai'" class="ghost-button" type="button" :disabled="loading" @click="transferToHuman"><Headset :size="16" />转人工</button>
              <button class="icon-button" type="button" title="查看会话" aria-label="查看会话" @click="openSession"><Info :size="18" /></button>
            </div>
          </div>

          <div ref="messageList" class="message-list" aria-live="polite">
            <div
              v-for="(message, index) in messages"
              :key="`${message.role}-${index}`"
              class="message"
              :class="message.role"
            >
              <div v-if="message.role !== 'system'" class="message-avatar">
                <UserRound v-if="message.role === 'user'" :size="16" />
                <Headset v-else-if="message.role === 'human'" :size="16" />
                <Bot v-else :size="16" />
              </div>
              <div class="message-body">
                <div v-if="message.role !== 'system'" class="message-meta"><span>{{ messageLabel(message) }}</span><time>{{ formatTime(message.created_at) }}</time></div>
                <div class="message-bubble"><MessageContent :content="message.content" :formatted="message.role === 'assistant' || message.role === 'human'" /></div>
              </div>
            </div>
            <div v-if="sending" class="sending-state"><RefreshCw :size="14" class="spinning" />{{ conversationMode === 'ai' ? '正在处理' : '正在发送' }}</div>
          </div>

          <form class="composer" @submit.prevent="sendMessage">
            <input v-model="inputMessage" aria-label="用户消息" type="text" :placeholder="conversationMode === 'ai' ? '输入您的问题…' : '向人工客服发送消息…'" maxlength="4000" :disabled="loading" />
            <button type="submit" :disabled="loading || !inputMessage.trim()"><Send :size="16" />发送</button>
          </form>
        </div>

        <aside class="panel session-inspector" :class="{ 'is-open': inspectorOpen }">
          <div class="panel-header">
            <div>
              <h3>会话详情</h3>
            </div>
            <button class="icon-button inspector-close" title="关闭会话详情" aria-label="关闭会话详情" @click="inspectorOpen = false"><X :size="17" /></button>
          </div>
          <div class="visitor-profile"><div class="visitor-avatar"><UserRound :size="23" /></div><strong>{{ sessionDetail?.session?.customer_name || '访客' }}</strong><span>{{ sessionDetail?.session?.phone || '暂无联系信息' }}</span></div>
          <dl class="session-fields">
            <div><dt>服务状态</dt><dd><span class="service-badge" :class="conversationMode">{{ conversationMode === 'human' ? '人工接待中' : conversationStatus }}</span></dd></div>
            <div><dt>接待客服</dt><dd>{{ sessionDetail?.session?.assigned_agent || 'AI 客服' }}</dd></div>
            <div><dt>消息数量</dt><dd>{{ sessionDetail?.messages?.length || 0 }}</dd></div>
            <div><dt>当前订单</dt><dd>{{ currentOrder || '未关联' }}</dd></div>
          </dl>
          <div class="inspector-section"><div class="section-heading"><h4>会话编号</h4><button class="icon-button" title="复制会话编号" aria-label="复制会话编号" @click="copySession"><Copy :size="15" /></button></div><code class="session-code">{{ sessionId }}</code></div>
          <div v-if="sessionDetail?.messages?.length" class="inspector-section"><h4>最近动态</h4><div class="activity-list"><div v-for="message in sessionDetail.messages.slice(-3).reverse()" :key="message.id" class="activity-item"><span class="activity-dot" :class="message.role"></span><div><strong>{{ messageLabel(message) }}</strong><p>{{ messagePreview(message.content) }}</p><time>{{ formatTime(message.created_at) }}</time></div></div></div></div>
        </aside>
      </section>

      <LiveSupport v-if="activeView === 'support'" />

      <section v-if="activeView === 'reviews'" class="view-grid review-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>待审核工单 <span class="queue-count">{{ reviews.length }}</span></h3>
            </div>
            <button class="icon-button" type="button" title="刷新审核列表" aria-label="刷新审核列表" :disabled="loading" @click="refreshReviews()"><RefreshCw :size="17" :class="{ spinning: loading }" /></button>
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
              <span class="record-meta"><span>{{ review.order_no || "无订单" }}</span><span class="service-badge waiting_human">待处理</span></span>
              <p>{{ review.review_reason }}</p>
            </button>
          </div>
          <div v-if="!reviews.length" class="empty">暂无待审核工单</div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>审核处理</h3>
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
            <label class="field-label" for="reviewer-name">审核人员</label><input id="reviewer-name" v-model="reviewerName" class="field" type="text" />
            <label class="field-label" for="review-reply">处理回复</label><textarea id="review-reply" v-model="reviewerReply" class="field textarea"></textarea>
            <div class="button-row">
              <button class="primary-button" type="button" :disabled="loading || !reviewerReply.trim()" @click="handleReview('approve')"><Check :size="16" />处理完成</button>
              <button class="danger-button" type="button" :disabled="loading || !reviewerReply.trim()" @click="handleReview('reject')"><X :size="16" />驳回</button>
            </div>
          </template>
          <div v-else class="empty"><ClipboardCheck :size="32" /><strong>未选择审核单</strong></div>
        </div>
      </section>

      <section v-if="activeView === 'traces'" class="view-grid trace-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>最近执行轨迹</h3>
            </div>
            <button class="icon-button" type="button" title="刷新执行轨迹" aria-label="刷新执行轨迹" :disabled="loading" @click="refreshTraces()"><RefreshCw :size="17" :class="{ spinning: loading }" /></button>
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
              <span class="record-meta"><span class="service-badge" :class="trace.final_action === 'human_review' ? 'waiting_human' : 'ai'">{{ trace.final_action }}</span><time>{{ formatTime(trace.created_at) }}</time></span>
              <p>{{ trace.user_message }}</p>
            </button>
          </div>
          <div v-if="!traces.length" class="empty"><Workflow :size="32" /><strong>暂无执行轨迹</strong></div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>节点明细</h3>
            </div>
          </div>
          <div v-if="selectedTrace" class="steps">
            <div v-for="(step, index) in selectedTrace.trace_steps || []" :key="index" class="step">
              <span>{{ index + 1 }}</span>
              <div>
                <strong>{{ formatStepName(step) }}</strong>
                <p class="step-summary">{{ step.message || step.reason || step.review_reason || step.final_action || '' }}</p>
                <details><summary>节点数据</summary><pre>{{ JSON.stringify(step, null, 2) }}</pre></details>
              </div>
            </div>
          </div>
          <div v-else class="empty"><Workflow :size="32" /><strong>未选择执行记录</strong></div>
        </div>
      </section>

      <section v-if="activeView === 'knowledge'" class="view-grid knowledge-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>知识库文件</h3>
            </div>
            <button class="icon-button" type="button" title="刷新文件列表" aria-label="刷新文件列表" :disabled="loading" @click="refreshKnowledge()"><RefreshCw :size="17" /></button>
          </div>

          <div class="file-list">
            <div v-for="file in knowledgeFiles" :key="file.path" class="file-item">
              <FileText :size="18" /><strong>{{ file.file_name }}</strong>
              <span>{{ formatSize(file.size) }}</span>
            </div>
          </div>
          <div v-if="!knowledgeFiles.length" class="empty"><BookOpen :size="32" /><strong>暂无知识文件</strong></div>
          <button class="wide-button" type="button" :disabled="loading" @click="doReindex">
            <RefreshCw :size="16" :class="{ spinning: loading }" />重新构建向量库
          </button>
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>知识库检索</h3>
            </div>
          </div>
          <form class="search-box" @submit.prevent="doKnowledgeSearch">
            <input v-model="knowledgeQuery" aria-label="知识库检索问题" type="text" placeholder="输入政策问题" />
            <button type="submit" :disabled="loading || !knowledgeQuery.trim()"><Search :size="16" />检索</button>
          </form>
          <div class="compact-list">
            <div v-for="(doc, index) in knowledgeResults" :key="index" class="compact-item">
              <div class="section-heading"><strong><FileText :size="15" />{{ doc.source }}</strong><span class="score-label">{{ Number(doc.score).toFixed(3) }}</span></div>
              <MessageContent :content="doc.text" />
            </div>
          </div>
          <div v-if="!knowledgeResults.length" class="empty"><Search :size="32" /><strong>暂无检索结果</strong></div>
        </div>
      </section>

      <section v-if="activeView === 'system'" class="view-grid system-grid">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h3>系统自检</h3>
              <p v-if="lastCheckedAt">最近检查 {{ lastCheckedAt.toLocaleTimeString('zh-CN') }}</p>
            </div>
            <button class="ghost-button" type="button" :disabled="loading" @click="refreshSystem()"><RefreshCw :size="16" :class="{ spinning: loading }" />重新检查</button>
          </div>

          <div v-if="systemStatus" class="system-summary"><Server :size="21" /><strong>{{ healthyServices }} / {{ serviceEntries.length }} 项服务正常</strong></div>
          <div v-if="systemStatus" class="status-grid">
            <div v-for="(item, key) in systemStatus" :key="key" class="status-card">
              <div class="service-icon"><Database v-if="['postgres', 'milvus'].includes(key)" :size="22" /><Bot v-else :size="22" /></div>
              <div class="section-heading"><strong>{{ key }}</strong><span class="service-badge" :class="item.success ? 'human' : 'waiting_human'"><span class="badge-dot"></span>{{ item.success ? '正常' : '异常' }}</span></div>
              <p>{{ item.message }}</p>
            </div>
          </div>
          <div v-else class="empty">暂无系统状态</div>
        </div>
      </section>
    </main>
  </div>
</template>
