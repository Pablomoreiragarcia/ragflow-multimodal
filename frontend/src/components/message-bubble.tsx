"use client";

import * as React from "react";
import { ChatMarkdown } from "@/components/chat-markdown";

type Attachment = {
  id: string;
  kind: string;
  path: string;
  title?: string | null;
};

type Props = {
  role: string;
  content: string;
  attachments: Attachment[];
};

function downloadUrl(att: Attachment) {
  if (att.kind === "image") {
    return `/api/images/download?path=${encodeURIComponent(att.path)}`;
  }
  if (att.kind === "table") {
    return `/api/tables/download?path=${encodeURIComponent(att.path)}`;
  }
  return null;
}

export function MessageBubble({ role, content, attachments }: Props) {
  const imageAtts = attachments.filter((a) => a.kind === "image");
  const tableAtts = attachments.filter((a) => a.kind === "table");

  const isAssistant = role !== "user"; // o role === "assistant" si lo prefieres

  return (
    <div className={role === "user" ? "ml-auto max-w-[65%]" : "mr-auto max-w-[65%]"}>
      <div className="rounded-xl bg-muted px-4 py-3 text-sm">
        {/* CONTENIDO: markdown para assistant, texto plano para user */}
        {isAssistant ? (
          <ChatMarkdown text={content ?? ""} />
        ) : (
          <div className="whitespace-pre-wrap">{content}</div>
        )}

        {/* Render inline de imágenes (una o varias) */}
        {imageAtts.length > 0 && (
          <div className="mt-3 space-y-3">
            {imageAtts.map((att) => {
              const url = downloadUrl(att);
              if (!url) return null;
              return (
                <div key={att.id} className="overflow-hidden rounded-lg border bg-background">
                  <img src={url} alt={att.title ?? "Imagen"} className="block h-auto w-full" />
                </div>
              );
            })}
          </div>
        )}

        {/* Acciones minimalistas: solo lo que exista */}
        {(imageAtts.length > 0 || tableAtts.length > 0) && (
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
            {imageAtts.map((att) => {
              const url = downloadUrl(att);
              if (!url) return null;
              return (
                <React.Fragment key={`img-actions-${att.id}`}>
                  <a className="hover:underline" href={url} target="_blank" rel="noreferrer">
                    Ver imagen
                  </a>
                  <a className="hover:underline" href={url} download>
                    Descargar
                  </a>
                </React.Fragment>
              );
            })}

            {tableAtts.map((att) => {
              const url = downloadUrl(att);
              if (!url) return null;
              return (
                <React.Fragment key={`tbl-actions-${att.id}`}>
                  <a className="hover:underline" href={url} target="_blank" rel="noreferrer">
                    Ver CSV
                  </a>
                  <a className="hover:underline" href={url} download>
                    Descargar
                  </a>
                </React.Fragment>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
