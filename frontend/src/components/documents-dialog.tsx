// frontend/src/components/documents-dialog.tsx
"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import { apiPostForm } from "@/lib/api";

type DocumentItem = {
  id: string;
  original_filename?: string | null;
  status: "pending" | "processing" | "ready" | "failed" | string;
  meta?: any;
  created_at?: string;
  updated_at?: string;
};

type AssetItem = {
  id: string;
  type: "table" | "image" | string;
  page?: number | null;
  storage_key: string;
  meta?: any;
  created_at?: string;
};

type DocumentDetail = DocumentItem & { assets: AssetItem[] };

function downloadUrlForAsset(a: AssetItem) {
  const p = encodeURIComponent(a.storage_key);
  if (a.type === "image") return `/api/images/download?path=${p}`;
  if (a.type === "table") return `/api/tables/download?path=${p}`;
  return null;
}

export function DocumentsLibraryDialog() {
  const dialogRef = React.useRef<HTMLDialogElement | null>(null);
  const queryClient = useQueryClient();

  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  // ✅ NUEVO: abrir desde cualquier parte disparando un evento global
  React.useEffect(() => {
    const handler = () => dialogRef.current?.showModal();
    window.addEventListener("open-documents-dialog", handler);
    return () => window.removeEventListener("open-documents-dialog", handler);
  }, []);

  const docsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet<DocumentItem[]>("/api/documents/"),
    refetchInterval: (q) => {
      const docs = (q.state.data as DocumentItem[] | undefined) ?? [];
      const hasRunning = docs.some((d) => d.status === "pending" || d.status === "processing");
      return hasRunning ? 2000 : false;
    },
  });

  const detailQuery = useQuery({
    queryKey: ["document", selectedId],
    queryFn: () => apiGet<DocumentDetail>(`/api/documents/${selectedId}`),
    enabled: !!selectedId,
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return apiPostForm<DocumentItem>("/api/documents/ingest/", fd);
    },
    onSuccess: (doc) => {
      setSelectedId(doc.id);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["document", doc.id] });
    },
  });

  const reindexMutation = useMutation({
    mutationFn: async (docId: string) => {
      const res = await fetch(`/api/documents/${docId}/reindex/`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (selectedId) queryClient.invalidateQueries({ queryKey: ["document", selectedId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (docId: string) => {
      const res = await fetch(`/api/documents/${docId}/`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `HTTP ${res.status}`));
      return true;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setSelectedId(null);
    },
  });

  const open = () => dialogRef.current?.showModal();
  const close = () => dialogRef.current?.close();

  return (
    <>
      <button
        type="button"
        onClick={open}
        className="mt-3 w-full rounded-md border px-3 py-2 text-sm"
      >
        Documentos
      </button>

      <dialog
        ref={dialogRef}
        // ✅ Mantienes centrado: perfecto
        className="
          fixed left-1/2 top-1/2 m-0
          w-[min(980px,95vw)]
          -translate-x-1/2 -translate-y-1/2
          rounded-xl border p-0
          bg-background shadow-lg
          backdrop:bg-black/40
        "
        // ✅ NUEVO: click fuera (backdrop) cierra
        onClick={(e) => {
          if (e.target === e.currentTarget) close();
        }}
        // ✅ NUEVO: evita que un submit accidental cierre raro; permite Esc por defecto
        onCancel={(e) => {
          // Por defecto Esc cierra; no hacemos preventDefault.
          // Si quisieras bloquear Esc: e.preventDefault()
        }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="text-sm font-semibold">Documentos (ingesta)</div>
          <button type="button" onClick={close} className="rounded-md border px-3 py-1 text-sm">
            Cerrar
          </button>
        </div>

        {/* Body con scroll */}
        <div className="max-h-[calc(90vh-52px)] overflow-y-auto">
          <div className="grid gap-0 md:grid-cols-[360px_1fr]">
            {/* Left */}
            <div className="border-b md:border-b-0 md:border-r">
              <div className="p-4">
                <label className="block text-xs font-medium opacity-70">Subir PDF</label>
                <input
                  type="file"
                  accept="application/pdf"
                  className="mt-2 block w-full text-sm"
                  disabled={uploadMutation.isPending}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadMutation.mutate(f);
                    e.currentTarget.value = "";
                  }}
                />
                {uploadMutation.isError && (
                  <div className="mt-2 text-xs text-red-500">{(uploadMutation.error as Error).message}</div>
                )}
                {uploadMutation.isPending && <div className="mt-2 text-xs opacity-70">Subiendo…</div>}
              </div>

              <div className="px-4 pb-3 text-xs font-medium opacity-70">
                {docsQuery.isLoading ? "Cargando…" : `Documentos: ${(docsQuery.data ?? []).length}`}
              </div>

              <div className="max-h-[60vh] overflow-y-auto px-2 pb-3">
                {(docsQuery.data ?? []).map((d) => {
                  const active = d.id === selectedId;
                  return (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => setSelectedId(d.id)}
                      className={[
                        "mb-2 w-full rounded-md border px-3 py-2 text-left text-sm",
                        active ? "bg-black/5" : "bg-white",
                      ].join(" ")}
                    >
                      <div className="truncate font-medium">{d.original_filename ?? d.id}</div>
                      <div className="mt-1 flex items-center justify-between text-xs opacity-70">
                        <span>{d.status}</span>
                        <span className="truncate">{d.updated_at ?? ""}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Right */}
            <div className="p-4">
              {!selectedId && <div className="text-sm opacity-70">Selecciona un documento para ver su estado y assets.</div>}

              {selectedId && detailQuery.isLoading && <div className="text-sm opacity-70">Cargando detalle…</div>}

              {selectedId && detailQuery.isError && (
                <div className="text-sm text-red-500">Error: {(detailQuery.error as Error).message}</div>
              )}

              {selectedId && detailQuery.data && (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold">
                        {detailQuery.data.original_filename ?? detailQuery.data.id}
                      </div>
                      <div className="text-xs opacity-70">
                        Estado: {detailQuery.data.status} · {detailQuery.data.updated_at ?? ""}
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="rounded-md border px-3 py-1 text-sm"
                        onClick={() => reindexMutation.mutate(detailQuery.data!.id)}
                        disabled={reindexMutation.isPending}
                      >
                        {reindexMutation.isPending ? "Reindex…" : "Reindex"}
                      </button>

                      <button
                        type="button"
                        className="rounded-md border px-3 py-1 text-sm"
                        onClick={() => deleteMutation.mutate(detailQuery.data!.id)}
                        disabled={deleteMutation.isPending}
                      >
                        {deleteMutation.isPending ? "Borrando…" : "Eliminar"}
                      </button>
                    </div>
                  </div>

                  {detailQuery.data.status === "failed" && (
                    <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm">
                      <div className="font-medium">Fallo en ingesta</div>
                      <div className="mt-1 text-xs opacity-80">{detailQuery.data.meta?.error ?? "Sin detalle de error en meta."}</div>
                    </div>
                  )}

                  <div className="rounded-md border p-3">
                    <div className="text-sm font-medium">Assets</div>
                    <div className="mt-2 space-y-2">
                      {detailQuery.data.assets?.length ? (
                        detailQuery.data.assets.map((a) => {
                          const url = downloadUrlForAsset(a);
                          return (
                            <div key={a.id} className="flex items-center justify-between gap-3 rounded-md border p-2">
                              <div className="min-w-0">
                                <div className="truncate text-sm">
                                  <span className="font-medium">{a.type}</span>
                                  {a.page ? <span className="opacity-70"> · pág {a.page}</span> : null}
                                </div>
                                <div className="truncate text-xs opacity-70">{a.storage_key}</div>
                              </div>

                              <div className="flex shrink-0 gap-2">
                                {url ? (
                                  <a className="rounded-md border px-3 py-1 text-sm" href={url} target="_blank" rel="noreferrer">
                                    Abrir
                                  </a>
                                ) : null}
                                {url ? (
                                  <a className="rounded-md border px-3 py-1 text-sm" href={url} download>
                                    Descargar
                                  </a>
                                ) : null}
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="text-sm opacity-70">
                          {detailQuery.data.status === "ready"
                            ? "No hay assets. (Revisa extracción)"
                            : "Aún no hay assets (pendiente/procesando)."}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </dialog>
    </>
  );
}
