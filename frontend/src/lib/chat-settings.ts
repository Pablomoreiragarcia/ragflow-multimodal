export type ChatSettings = {
  model: string; // hoy: solo UI
  topK: number;  // se envía al backend como top_k
};

const PREFIX = "ragflow:chatSettings:";

export function loadChatSettings(conversationId: string | undefined | null): ChatSettings {
  const fallback: ChatSettings = { model: "default", topK: 5 };
  if (!conversationId) return fallback;

  try {
    const raw = localStorage.getItem(PREFIX + conversationId);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<ChatSettings>;

    const topK = clampInt(parsed.topK ?? fallback.topK, 1, 50);
    const model = (parsed.model ?? fallback.model).trim() || fallback.model;

    return { model, topK };
  } catch {
    return fallback;
  }
}

export function saveChatSettings(conversationId: string, s: ChatSettings) {
  const normalized: ChatSettings = {
    model: (s.model ?? "default").trim() || "default",
    topK: clampInt(s.topK ?? 5, 1, 50),
  };
  localStorage.setItem(PREFIX + conversationId, JSON.stringify(normalized));
}

function clampInt(x: unknown, min: number, max: number) {
  const n = typeof x === "number" ? x : Number(x);
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, Math.trunc(n)));
}
