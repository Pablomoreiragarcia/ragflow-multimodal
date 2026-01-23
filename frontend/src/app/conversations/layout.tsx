// frontend/src/app/conversations/layout.tsx
"use client";

import Link from "next/link";
import { useMemo, useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { loadChatSettings, saveChatSettings } from "@/lib/chat-settings";

import { DocumentsLibraryDialog } from "@/components/documents-dialog";
import { ConversationDocsDialog } from "@/components/conversation-docs-dialog";

type ConversationSummary = { id: string; title: string | null; updated_at: string };
type ConversationCreate = { title?: string; scope?: string; deleted?: boolean; model?: string; top_k?: number; };

type ModelOption = { id: string; label?: string };
type ModelsResponse = { models: Array<ModelOption | string> };

const FALLBACK_MODELS: ModelOption[] = [{ id: "gpt-4.1-mini", label: "gpt-4.1-mini (fallback)" }];

export default function ConversationsLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();

  const [q, setQ] = useState("");
  const [newOpen, setNewOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("Nueva conversación");
  const [newModel, setNewModel] = useState<string>("");
  const [newTopK, setNewTopK] = useState<number>(5);

  const { data, isLoading, error } = useQuery({
    queryKey: ["conversations"],
    queryFn: () => apiGet<ConversationSummary[]>("/api/conversations"),
  });

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: () => apiGet<ModelsResponse>("/api/rag/models"),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const models: ModelOption[] = useMemo(() => {
    const m = modelsQuery.data?.models;
    if (!m || !Array.isArray(m) || m.length === 0) return FALLBACK_MODELS;

    const normalized = m
      .map((x) => {
        if (typeof x === "string") return { id: x, label: x };
        if (x && typeof x === "object" && "id" in x) return { id: String(x.id), label: x.label ?? String(x.id) };
        return null;
      })
      .filter(Boolean) as ModelOption[];

    return normalized.length ? normalized : FALLBACK_MODELS;
  }, [modelsQuery.data]);

  useEffect(() => {
    if (!newOpen) return;

    // si ya hay modelo seleccionado, no lo machacamos
    if (newModel) return;

    // intenta elegir el que contenga "(default)" si existe
    const def =
      models.find((m) => (m.label ?? "").toLowerCase().includes("default"))?.id ??
      models[0]?.id ??
      "gpt-4.1-mini";

    setNewModel(def);
  }, [newOpen, models, newModel]);

  const createMutation = useMutation({
    mutationFn: async (args: { title: string; model: string; topK: number }) => {
      const payload: ConversationCreate = { title: args.title, scope: "default", deleted: false, model: args.model, top_k: args.topK };
      const created = await apiPost<ConversationCreate, ConversationSummary>("/api/conversations", payload);
      return { created, args };
    },
    onSuccess: ({ created, args }) => {
      saveChatSettings(created.id, { model: args.model, topK: args.topK });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setNewOpen(false);

      // Opcional: autoabrir selector de docs al entrar al chat
      sessionStorage.setItem("openConvDocsFor", created.id);

      router.push(`/conversations/${created.id}`);
    },
  });

  const filtered = useMemo(() => {
    const list = data ?? [];
    const term = q.trim().toLowerCase();
    if (!term) return list;
    return list.filter((c) => (c.title ?? "").toLowerCase().includes(term) || c.id.toLowerCase().includes(term));
  }, [data, q]);

  return (
    <div className="flex h-screen">
      <aside className="w-80 border-r flex flex-col">
        <div className="p-4 flex items-center justify-between">
          <div className="font-semibold">Conversaciones</div>
          <Button size="sm" onClick={() => setNewOpen((v) => !v)}>Nueva</Button>
        </div>

        {newOpen && (
          <div className="px-4 pb-4 space-y-2">
            <Input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Título" />

            <div className="grid grid-cols-2 gap-2">
              {/* SELECT PRO */}
              <div className="space-y-1">
                <div className="text-xs opacity-70">Modelo</div>
                <select
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  disabled={modelsQuery.isLoading}
                >
                  {modelsQuery.isLoading ? (
                    <option value="">Cargando modelos…</option>
                  ) : modelsQuery.isError ? (
                    <>
                      <option value="gpt-4.1-mini">gpt-4.1-mini (fallback)</option>
                    </>
                  ) : (
                    models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label ?? m.id}
                      </option>
                    ))
                  )}
                </select>

                {/* opcional: feedback error */}
                {modelsQuery.isError && (
                  <div className="text-xs text-destructive">
                    No se pudieron cargar modelos; usando fallback.
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <div className="text-xs opacity-70">k</div>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={newTopK}
                  onChange={(e) => setNewTopK(Number(e.target.value))}
                />
              </div>
            </div>

            <Button
              className="w-full"
              disabled={createMutation.isPending || !newTitle.trim() || !newModel}
              onClick={() => createMutation.mutate({ title: newTitle, model: newModel, topK: newTopK })}
            >
              Crear conversación
            </Button>
          </div>
        )}

        <div className="px-4 pb-4">
          <Input placeholder="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>

        <Separator />

        <div className="flex-1 overflow-hidden hover:overflow-y-auto p-2">
          {isLoading && <div className="p-2 text-sm opacity-70">Cargando…</div>}
          {error && <div className="p-2 text-sm">Error: {(error as Error).message}</div>}

          <div className="space-y-1">
            {filtered.map((c) => {
              const href = `/conversations/${c.id}`;
              const active = pathname === href;
              return (
                <Link
                  key={c.id}
                  href={href}
                  className={["block rounded-md px-3 py-2 text-sm", active ? "bg-muted" : "hover:bg-muted/60"].join(" ")}
                  onClick={() => {
                    const s = loadChatSettings(c.id);
                    saveChatSettings(c.id, s);
                  }}
                >
                  <div className="font-medium">{c.title ?? "(sin título)"}</div>
                  <div className="text-xs opacity-70">{c.updated_at}</div>
                </Link>
              );
            })}
          </div>
        </div>

        <Separator />
        <div className="p-2">
          {/* Este es el modal de INGESTA/BIBLIOTECA */}
          <DocumentsLibraryDialog />
        </div>
      </aside>

      <main className="flex-1 min-w-0">
        {children}
      </main>

      {/* Montado una sola vez: selector por conversación (sin botón aquí) */}
      <ConversationDocsDialog />
    </div>
  );
}
