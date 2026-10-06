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
    throw new Error(data.message || "请求失败");
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

export function searchKnowledge(query, topK = 3) {
  return request(`/knowledge/search?query=${encodeURIComponent(query)}&top_k=${topK}`);
}

export function reindexKnowledge() {
  return request("/knowledge/reindex", {
    method: "POST",
    body: JSON.stringify({}),
  });
}
