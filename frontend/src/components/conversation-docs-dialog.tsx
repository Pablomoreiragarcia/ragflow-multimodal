// frontend/src/components/conversation-docs-dialog.tsx
"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

import type { ConversationDetail, DocumentItem, } from "@/lib/types";

type ConvDocs = { doc_ids: string[]; invalid_doc_ids?: string[] };

export function ConversationDocsDialog() {
  const dialogRef = React.useRef<HTMLDialogElement | null>(null);
  const queryClient = useQueryClient();

  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [activeDocIds, setActiveDocIds] = React.useState<string[]>([]);
  const [lastInvalid, setLastInvalid] = React.useState<string[]>([]);

  // 1) Abrir modal por evento (desde header “Editar”, o tras crear conversación)
  React.useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<{ conversationId?: string }>;
      const cid = ce.detail?.conversationId;
      if (!cid) return;

      setConversationId(cid);
      setLastInvalid([]);

      // 1) hidrata desde cache para que los checks salgan bien al instante
      const cached = queryClient.getQueryData<ConvDocs>(["conversation-docs", cid]);
      setActiveDocIds(Array.isArray(cached?.doc_ids) ? cached!.doc_ids : []);

      // 2) refresca para sanear si hubo borrados/reindex
      queryClient.invalidateQueries({ queryKey: ["conversation-docs", cid] });

      // si quieres limpiar el error visual:
      saveDocsMutation.reset();

      dialogRef.current?.showModal();
    };

    window.addEventListener("open-conversation-docs-dialog", handler as any);
    return () => window.removeEventListener("open-conversation-docs-dialog", handler as any);
  }, [queryClient]);

  const close = () => dialogRef.current?.close();

  // 2) Cargar lista de documentos y filtrar ready
  const docsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet<DocumentItem[]>("/api/documents/"),
  });

  const readyDocs = React.useMemo(() => {
    return (docsQuery.data ?? []).filter((d) => d.status === "ready");
  }, [docsQuery.data]);

  // 3) Cargar doc_ids activos de la conversación
  const convDocsQuery = useQuery({
    queryKey: ["conversation-docs", conversationId],
    queryFn: () => apiGet<ConvDocs>(`/api/conversations/${conversationId}/docs/`),
    enabled: !!conversationId,
    placeholderData: () =>
      conversationId
        ? queryClient.getQueryData<ConvDocs>(["conversation-docs", conversationId])
        : undefined,
  });

  React.useEffect(() => {
    if (!conversationId) return;

    const ids = convDocsQuery.data?.doc_ids ?? [];
    const invalid = convDocsQuery.data?.invalid_doc_ids ?? [];

    setActiveDocIds(Array.isArray(ids) ? ids : []);
    setLastInvalid(Array.isArray(invalid) ? invalid : []);
  }, [conversationId, convDocsQuery.dataUpdatedAt]);

  // 4) Guardar selección
  const saveDocsMutation = useMutation({
    mutationFn: async (docIds: string[]) => {
      if (!conversationId) return;
      const res = await fetch(`/api/conversations/${conversationId}/docs/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ doc_ids: docIds }),
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
      return (await res.json()) as ConvDocs;
    },
    onSuccess: (data) => {
      if (!conversationId) return;

      const cleaned = Array.isArray(data?.doc_ids) ? data.doc_ids : [];
      const invalid = Array.isArray(data?.invalid_doc_ids) ? data.invalid_doc_ids : [];

      setActiveDocIds(cleaned);
      setLastInvalid(invalid);

      queryClient.setQueryData(["conversation-docs", conversationId], { doc_ids: cleaned });
      queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
    },
  });

  function toggleDoc(docId: string) {
    const next = activeDocIds.includes(docId)
      ? activeDocIds.filter((x) => x !== docId)
      : [...activeDocIds, docId];

    setActiveDocIds(next);

    // 1) Cache del endpoint /docs/
    queryClient.setQueryData<{ doc_ids: string[] }>(
      ["conversation-docs", conversationId],
      { doc_ids: next }
    );

    // 2) Cache del detalle de conversación (si el header lo usa o lo vas a usar)
    queryClient.setQueryData<ConversationDetail>(
      ["conversation", conversationId],
      (prev) => {
        if (!prev) return prev as any;
        return { ...prev, doc_ids: next };
      }
    );

    saveDocsMutation.mutate(next);
  }
    
  return (
    <dialog
      ref={dialogRef}
      className="
        fixed left-1/2 top-1/2 m-0
        w-[min(720px,95vw)]
        -translate-x-1/2 -translate-y-1/2
        rounded-xl border p-0
        bg-background shadow-lg
        backdrop:bg-black/40
      "
    >
      {lastInvalid.length > 0 && (
        <div className="mt-3 rounded-md border bg-yellow-50 p-3 text-sm">
          Se han eliminado de la selección {lastInvalid.length} documento(s) que ya no existen o no están en <b>ready</b>.
        </div>
      )}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="text-sm font-semibold">
          Documentos activos {conversationId ? `· ${conversationId}` : ""}
        </div>
        <button type="button" onClick={close} className="rounded-md border px-3 py-1 text-sm">
          Cerrar
        </button>
      </div>

      <div className="max-h-[calc(90vh-52px)] overflow-y-auto p-4">
        {!conversationId ? (
          <div className="text-sm opacity-70">No hay conversación activa.</div>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm">
                Selecciona documentos <span className="opacity-70">(solo status=ready)</span>
              </div>
              <div className="text-xs opacity-70">
                {saveDocsMutation.isPending ? "Guardando…" : `Seleccionados: ${activeDocIds.length}`}
              </div>
            </div>

            {docsQuery.isLoading && <div className="text-sm opacity-70">Cargando documentos…</div>}
            {docsQuery.isError && (
              <div className="text-sm text-red-500">Error: {(docsQuery.error as Error).message}</div>
            )}

            <div className="space-y-2">
              {readyDocs.map((d) => {
                const checked = activeDocIds.includes(d.id);
                return (
                  <label
                    key={d.id}
                    className="flex items-start justify-between gap-3 rounded-md border p-3 text-sm"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium">{d.original_filename ?? d.id}</div>
                      <div className="mt-1 text-xs opacity-70">{d.updated_at ?? ""}</div>
                    </div>

                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={checked}
                      disabled={saveDocsMutation.isPending}
                      onChange={() => toggleDoc(d.id)}
                    />
                  </label>
                );
              })}

              {!readyDocs.length && !docsQuery.isLoading && (
                <div className="text-sm opacity-70">
                  No hay documentos en estado <span className="font-medium">ready</span>.
                </div>
              )}
            </div>

            {saveDocsMutation.isError && (
              <div className="mt-3 text-sm text-red-500">
                Error guardando: {(saveDocsMutation.error as Error).message}
              </div>
            )}
          </>
        )}
      </div>
    </dialog>
  );
}
