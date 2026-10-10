<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import { claimSupport, getSessionDetail, getSupportQueue, releaseSupport, sendSupportMessage } from "./api";
import MessageContent from "./MessageContent.vue";
import { Bot, Headset, MessageSquare, RefreshCw, Search, Send, UserRound, LogOut } from "lucide-vue-next";

const agentName = ref(localStorage.getItem("support_agent_name") || "人工客服A");
const queue = ref([]);
const selectedId = ref("");
const detail = ref(null);
const draft = ref("");
const busy = ref(false);
const error = ref("");
const conversationList = ref(null);
const queueFilter = ref("all");
const queueSearch = ref("");
const waitingCount = computed(() => queue.value.filter((item) => item.service_mode === "waiting_human").length);
const mineCount = computed(() => queue.value.filter((item) => item.service_mode === "human" && item.assigned_agent === agentName.value.trim()).length);
const filteredQueue = computed(() => queue.value.filter((item) => {
  const matchesFilter = queueFilter.value === "all"
    || (queueFilter.value === "waiting" && item.service_mode === "waiting_human")
    || (queueFilter.value === "mine" && item.service_mode === "human" && item.assigned_agent === agentName.value.trim());
  const query = queueSearch.value.trim().toLowerCase();
  return matchesFilter && (!query || [item.session_id, item.customer_name, item.last_message]
    .some((value) => value?.toLowerCase().includes(query)));
}));
const session = computed(() => detail.value?.session);
const ownsSession = computed(() => session.value?.service_mode === "human"
  && session.value.assigned_agent === agentName.value.trim());
let timer;
let refreshing = false;
let disposed = false;
let selectionVersion = 0;
let pendingReply = null;

function label(mode) {
  return { waiting_human: "等待接入", human: "人工接待中", ai: "AI 服务中" }[mode] || mode;
}

function messageLabel(message) {
  return { user: "用户", assistant: "AI 客服", human: message.sender_name || "人工客服", system: "接待通知" }[message.role] || message.role;
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

async function refresh() {
  if (refreshing || disposed) return;
  refreshing = true;
  const target = selectedId.value;
  const version = selectionVersion;
  try {
    const result = await getSupportQueue();
    if (disposed) return;
    queue.value = result.data || [];
    if (target) {
      const result = await getSessionDetail(target);
      if (!disposed && selectedId.value === target && selectionVersion === version && result.success) {
        const previousLast = detail.value?.messages?.at(-1)?.id;
        detail.value = result.data;
        if (previousLast !== result.data.messages.at(-1)?.id) {
          await nextTick();
          conversationList.value?.scrollTo({ top: conversationList.value.scrollHeight });
        }
      }
    }
  } catch (err) {
    if (!disposed) error.value = err.message || "接待列表更新失败";
  } finally {
    refreshing = false;
  }
}

async function selectSession(id) {
  const version = ++selectionVersion;
  if (id !== selectedId.value) pendingReply = null;
  selectedId.value = id;
  detail.value = null;
  draft.value = "";
  error.value = "";
  // A previous refresh may still be loading another conversation.
  try {
    const result = await getSessionDetail(id);
    if (!disposed && selectedId.value === id && selectionVersion === version && result.success) {
      detail.value = result.data;
      await nextTick();
      conversationList.value?.scrollTo({ top: conversationList.value.scrollHeight });
    }
  } catch (err) {
    if (selectedId.value === id) error.value = err.message;
  }
}

async function act(action) {
  if (busy.value || !session.value) return;
  const id = selectedId.value;
  const name = agentName.value.trim();
  if (!name) {
    error.value = "请填写客服名称";
    return;
  }
  const version = session.value.handoff_version;
  const content = draft.value.trim();
  if (action === "reply" && !content) return;
  busy.value = true;
  selectionVersion += 1;
  error.value = "";
  localStorage.setItem("support_agent_name", name);
  try {
    let result;
    if (action === "claim") result = await claimSupport(id, name);
    if (action === "release") result = await releaseSupport(id, { agent_name: name, handoff_version: version });
    if (action === "reply") {
      if (!pendingReply || pendingReply.sessionId !== id || pendingReply.payload.message !== content
        || pendingReply.payload.agent_name !== name || pendingReply.payload.handoff_version !== version) {
        pendingReply = { sessionId: id, payload: {
          agent_name: name, handoff_version: version, message: content, request_id: crypto.randomUUID(),
        } };
      }
      result = await sendSupportMessage(id, pendingReply.payload);
    }
    if (!result?.success) throw new Error(result?.message || "操作失败");
    if (action === "reply" && selectedId.value === id) {
      draft.value = "";
      pendingReply = null;
    }
    await selectSession(id);
    await refresh();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  refresh();
  timer = setInterval(() => { if (!document.hidden && !busy.value) refresh(); }, 1500);
});
onUnmounted(() => { disposed = true; clearInterval(timer); });
</script>

<template>
  <section class="support-workspace">
    <div class="support-toolbar">
      <Headset :size="18" /><label for="agent-name">接待客服</label>
      <input id="agent-name" v-model="agentName" class="field" maxlength="100" :disabled="busy" />
      <span class="support-workload"><span class="status-dot ok"></span>{{ mineCount }} 个接待中</span>
      <button class="icon-button" type="button" title="刷新队列" aria-label="刷新队列" :disabled="busy" @click="refresh"><RefreshCw :size="17" :class="{ spinning: busy }" /></button>
    </div>
    <div v-if="error" role="alert" class="notice error">{{ error }}</div>
    <div class="support-grid">
      <aside class="support-queue" aria-label="人工接待队列">
        <div class="queue-header"><h3>接待队列 <span class="queue-count">{{ queue.length }}</span></h3></div>
        <div class="queue-tabs" role="tablist" aria-label="队列筛选">
          <button role="tab" :aria-selected="queueFilter === 'all'" :class="{ active: queueFilter === 'all' }" @click="queueFilter = 'all'">全部</button>
          <button role="tab" :aria-selected="queueFilter === 'waiting'" :class="{ active: queueFilter === 'waiting' }" @click="queueFilter = 'waiting'">等待 {{ waitingCount }}</button>
          <button role="tab" :aria-selected="queueFilter === 'mine'" :class="{ active: queueFilter === 'mine' }" @click="queueFilter = 'mine'">我的 {{ mineCount }}</button>
        </div>
        <div class="queue-search"><Search :size="15" /><input v-model="queueSearch" aria-label="搜索接待会话" placeholder="搜索会话" /></div>
        <div class="queue-list">
        <button v-for="item in filteredQueue" :key="item.session_id" type="button"
          class="support-row" :class="{ selected: selectedId === item.session_id }"
          :disabled="busy" @click="selectSession(item.session_id)">
          <div class="queue-row-heading"><strong>{{ item.customer_name || `访客 ${item.session_id.slice(-6)}` }}</strong><time>{{ formatTime(item.waiting_since) }}</time></div>
          <small class="queue-session-id" :title="item.session_id">{{ item.session_id }}</small>
          <p>{{ item.last_message || "暂无消息" }}</p>
          <span class="queue-row-status"><span class="service-badge" :class="item.service_mode"><span class="badge-dot"></span>{{ label(item.service_mode) }}</span><small v-if="item.assigned_agent">{{ item.assigned_agent }}</small></span>
        </button>
        <div v-if="!filteredQueue.length" class="empty"><Headset :size="28" /><strong>{{ queue.length ? '没有匹配的会话' : '暂无待接待会话' }}</strong></div>
        </div>
      </aside>
      <div class="support-conversation">
        <template v-if="session">
          <div class="panel-header">
            <div class="support-title">
              <h3>{{ session.customer_name || "用户会话" }}</h3>
              <small>{{ session.session_id }}</small>
              <span class="service-badge" :class="session.service_mode"><span class="badge-dot"></span>{{ label(session.service_mode) }}</span>
            </div>
            <button v-if="session.service_mode === 'waiting_human'" class="primary-button" type="button"
              :disabled="busy || !agentName.trim()" @click="act('claim')"><Headset :size="16" />接入会话</button>
            <button v-if="ownsSession" class="ghost-button" type="button" :disabled="busy"
              @click="act('release')"><LogOut :size="16" />结束接待，交回 AI</button>
          </div>
          <div ref="conversationList" class="message-list" aria-live="polite">
            <div v-for="message in detail.messages" :key="message.id" class="message" :class="message.role">
              <div v-if="message.role !== 'system'" class="message-avatar"><UserRound v-if="message.role === 'user'" :size="16" /><Headset v-else-if="message.role === 'human'" :size="16" /><Bot v-else :size="16" /></div>
              <div class="message-body"><div v-if="message.role !== 'system'" class="message-meta"><span>{{ messageLabel(message) }}</span><time>{{ formatTime(message.created_at) }}</time></div><div class="message-bubble"><MessageContent :content="message.content" :formatted="message.role === 'assistant' || message.role === 'human'" /></div></div>
            </div>
          </div>
          <form v-if="ownsSession" class="composer" @submit.prevent="act('reply')">
            <input v-model="draft" aria-label="人工回复" placeholder="回复用户" maxlength="4000" :disabled="busy" />
            <button type="submit" :disabled="busy || !draft.trim()"><Send :size="16" />发送</button>
          </form>
          <div v-else-if="session.service_mode === 'human'" class="support-status">当前由 {{ session.assigned_agent }} 接待</div>
        </template>
        <div v-else class="empty conversation-empty"><div class="empty-icon"><MessageSquare :size="30" /></div><strong>未选择会话</strong><span>{{ waitingCount ? `${waitingCount} 个会话等待接入` : '当前没有等待中的会话' }}</span></div>
      </div>
    </div>
  </section>
</template>
