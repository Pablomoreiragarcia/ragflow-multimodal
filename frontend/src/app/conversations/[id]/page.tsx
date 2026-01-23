//frontend\src\app\conversations\[id]\page.tsx
"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { apiGet, apiPost } from "@/lib/api";
import { MessageBubble } from "@/components/message-bubble";

import type { ConversationDetail, Message, Attachment, AskResponse, } from "@/lib/types";
import { useMemo } from "react";

type ModelOption = { id: string; label: string };
type ModelsResponse = { models: Array<string | { id: string; label?: string }> };

const FALLBACK_MODELS: ModelOption[] = [{ id: "gpt-4.1-mini", label: "gpt-4.1-mini" }];

function sortMessagesStable(raw: Message[]) {
  const withIdx = raw.map((m, idx) => {
    const t = m.created_at ? Date.parse(m.created_at) : NaN;
    return { ...m, __idx: idx, __t: Number.isFinite(t) ? t : null };
  });

  withIdx.sort((a, b) => {
    const ta = a.__t;
    const tb = b.__t;
    if (ta != null && tb != null) {
      if (ta !== tb) return ta - tb;
      return a.__idx - b.__idx;
    }
    return a.__idx - b.__idx;
  });

  return withIdx.map(({ __idx, __t, ...m }) => m);
}

function normalizeAttachments(m: Message): Attachment[] {
  // Preferimos attachments[] (nuevo mundo).
  const atts = Array.isArray(m.attachments) ? m.attachments : [];
  if (atts.length) return atts;

  // Fallback legacy: si el backend aún devuelve image_path/table_path
  // pero no attachments, los convertimos para render.
  const legacy: Attachment[] = [];
  if (m.image_path) {
    legacy.push({
      id: `legacy-image-${m.id}`,
      kind: "image",
      path: m.image_path,
      title: "Imagen",
    });
  }
  if (m.table_path) {
    legacy.push({
      id: `legacy-table-${m.id}`,
      kind: "table",
      path: m.table_path,
      title: "Tabla",
    });
  }
  return legacy;
}

export default function ConversationPage() {
  const params = useParams<{ id: string | string[] }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;

  const queryClient = useQueryClient();

  // Conversación
  const convQuery = useQuery({
    queryKey: ["conversation", id],
    queryFn: () => apiGet<ConversationDetail>(`/api/conversations/${id}`),
    enabled: !!id,
  });

  // Modelos disponibles (desplegable)
  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: () => apiGet<ModelsResponse>("/api/rag/models"),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const modelOptions: ModelOption[] = useMemo(() => {
    const raw = modelsQuery.data?.models;
    if (!raw?.length) return FALLBACK_MODELS;

    const normalized: ModelOption[] = raw
      .map((x) => {
        if (typeof x === "string") return { id: x, label: x };
        if (x && typeof x === "object" && "id" in x) return { id: String(x.id), label: x.label ?? String(x.id) };
        return null;
      })
      .filter(Boolean) as ModelOption[];

    // dedupe por id (evita keys duplicadas si backend repite)
    const map = new Map<string, ModelOption>();
    for (const m of normalized) map.set(m.id, m);
    return Array.from(map.values());
  }, [modelsQuery.data]);

  const models = modelsQuery.data?.models?.length ? modelsQuery.data.models : ["default"];

  const [draft, setDraft] = React.useState("");
  const [topK, setTopK] = React.useState<number>(5);
  const [model, setModel] = React.useState<string>("default");

  const convDocsQuery = useQuery({
    queryKey: ["conversation-docs", id],
    queryFn: () => apiGet<{ doc_ids: string[] }>(`/api/conversations/${id}/docs/`),
    enabled: !!id,
  });

  const rawDocIds: any = convDocsQuery.data?.doc_ids;
  const activeDocIds = Array.isArray(rawDocIds) ? rawDocIds : [];
  const activeCount = activeDocIds.length;

  // Sincroniza settings desde conversación al cargar/cambiar de conversación
  React.useEffect(() => {
    if (!convQuery.data) return;
    setTopK(convQuery.data.top_k ?? 5);
    setModel((convQuery.data.model ?? "default") || "default");
  }, [convQuery.data?.id]);

  const orderedMessages = React.useMemo(() => {
    const raw = convQuery.data?.messages ?? [];
    return sortMessagesStable(raw);
  }, [convQuery.data?.messages]);

  // Scroll control
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const bottomRef = React.useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = React.useRef(true);

  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      const distanceToBottom = el.scrollHeight - (el.scrollTop + el.clientHeight);
      shouldAutoScrollRef.current = distanceToBottom < 120;
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  React.useEffect(() => {
    if (!shouldAutoScrollRef.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [orderedMessages.length]);

  React.useEffect(() => {
    if (!id) return;
    const want = sessionStorage.getItem("openConvDocsFor");
    if (want === id) {
      sessionStorage.removeItem("openConvDocsFor");
      window.dispatchEvent(new CustomEvent("open-conversation-docs-dialog", { detail: { conversationId: id } }));
    }
  }, [id]);

  // Envío
  const askMutation = useMutation({
    mutationFn: async (question: string) => {
      const clientMessageId =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

      const payload = {
        question,
        top_k: topK,
        model,
        conversation_id: id,
        client_message_id: clientMessageId,
      };

      return apiPost<typeof payload, AskResponse>("/api/rag/ask", payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversation", id] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] }); // sidebar reordenada
    },
  });

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = draft.trim();
    if (!q || askMutation.isPending) return;

    setDraft("");

    // Optimista: añade el user al cache para que se vea instantáneo
    queryClient.setQueryData<ConversationDetail>(["conversation", id], (prev) => {
      if (!prev) return prev as any;
      const optimisticMsg: Message = {
        id: `optimistic-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        role: "user",
        content: q,
        created_at: new Date().toISOString(),
        attachments: [],
        image_path: null,
        table_path: null,
      };
      return { ...prev, messages: [...(prev.messages ?? []), optimisticMsg] };
    });

    askMutation.mutate(q);
  };

  if (convQuery.isLoading) return <div className="p-6">Cargando conversación…</div>;
  if (convQuery.error) return <div className="p-6">Error: {(convQuery.error as Error).message}</div>;
  if (!convQuery.data) return <div className="p-6">No hay datos.</div>;

  const conv = convQuery.data;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="text-lg font-semibold">{conv.title ?? "Conversación"}</div>
        <div className="text-xs opacity-70 flex items-center gap-3">
          <span>{conv.id} · actualizado {conv.updated_at}</span>
          <span>
            Documentos activos: {activeCount === 0 ? "Auto" : activeCount}
          </span>
          <button
            type="button"
            className="underline"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("open-conversation-docs-dialog", { detail: { conversationId: id } })
              )
            }
          >
            Editar
          </button>
        </div>
      </div>

      {/* Mensajes */}
      <div className="flex-1 overflow-hidden">
        <div ref={scrollRef} className="h-full overflow-hidden px-6 py-4 hover:overflow-y-auto">
          <div className="space-y-3">
            {orderedMessages.map((m) => {
              const attachments = normalizeAttachments(m);

              return (
                <MessageBubble
                  key={m.id}
                  role={m.role}
                  content={m.content}
                  attachments={attachments}
                />
              );
            })}
            <div ref={bottomRef} />
          </div>
        </div>
      </div>

      {/* Composer fijo */}
      <form onSubmit={onSend} className="border-t bg-background px-6 py-4">
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="opacity-70">Modelo</span>
            <select
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={modelsQuery.isLoading}
              >
                {modelsQuery.isLoading ? (
                  <option value="">Cargando modelos…</option>
                ) : modelsQuery.isError ? (
                  FALLBACK_MODELS.map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))
                ) : (
                  modelOptions.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))
                )}
              </select>
          </div>

          <div className="flex items-center gap-2 text-sm">
            <span className="opacity-70">k</span>
            <input
              className="h-9 w-20 rounded-md border bg-background px-2 text-sm"
              type="number"
              min={1}
              max={50}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </div>

          {askMutation.isError && (
            <div className="text-sm text-red-500">Error: {(askMutation.error as Error).message}</div>
          )}
        </div>

        <div className="flex gap-2">
          <input
            className="h-11 flex-1 rounded-md border bg-background px-3 text-sm"
            placeholder="Escribe tu mensaje…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={askMutation.isPending}
          />
          <button
            type="submit"
            className="h-11 rounded-md border px-4 text-sm"
            disabled={askMutation.isPending}
          >
            {askMutation.isPending ? "Enviando…" : "Enviar"}
          </button>
        </div>
      </form>
    </div>
  );
}
