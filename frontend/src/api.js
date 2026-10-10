const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.message || (typeof data.detail === "string" ? data.detail : "请求失败"));
  }

  return data;
}

export function chat(message, sessionId) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      session_id: sessionId || null,
    }),
  });
}

export function systemCheck() {
  return request("/system/check");
}

export function getPendingReviews(limit = 20) {
  return request(`/reviews/pending?limit=${limit}`);
}

export function approveReview(payload) {
  return request("/reviews/approve", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function rejectReview(payload) {
  return request("/reviews/reject", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSessionDetail(sessionId) {
  return request(`/sessions/${encodeURIComponent(sessionId)}`);
}

export function getRecentTraces(limit = 20) {
  return request(`/traces/recent?limit=${limit}`);
}

export function getKnowledgeFiles() {
  return request("/knowledge/files");
}

export function searchKnowledge(query, topK) {
  const params = new URLSearchParams({ query });
  if (topK != null) {
    params.set("top_k", String(topK));
  }
  return request(`/knowledge/search?${params.toString()}`);
}

export function reindexKnowledge() {
  return request("/knowledge/reindex", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function requestHandoff(sessionId) {
  return request("/handoffs/request", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId || null }),
  });
}

export function getSupportQueue() {
  return request("/handoffs");
}

export function claimSupport(sessionId, agentName) {
  return request(`/handoffs/${encodeURIComponent(sessionId)}/claim`, {
    method: "POST",
    body: JSON.stringify({ agent_name: agentName }),
  });
}

export function sendSupportMessage(sessionId, payload) {
  return request(`/handoffs/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function releaseSupport(sessionId, payload) {
  return request(`/handoffs/${encodeURIComponent(sessionId)}/release`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
