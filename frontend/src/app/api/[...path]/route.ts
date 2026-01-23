// frontend/src/app/api/[...path]/route.ts

import { NextRequest } from "next/server";

const BACKEND = (process.env.BACKEND_INTERNAL_ORIGIN || "http://backenddjango:8000").replace(/\/$/, "");

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
]);

function buildBackendUrl(pathSegments: string[], search: string) {
  const path = pathSegments.join("/");
  const normalized = path.endsWith("/") ? path : `${path}/`;
  return `${BACKEND}/api/${normalized}${search}`;
}

async function proxy(req: NextRequest, ctx: any) {
  // Soporta params sync o async (según versión/runtime)
  const params = await Promise.resolve(ctx?.params);
  const pathSegments: string[] = Array.isArray(params?.path) ? params.path : [];

  const url = new URL(req.url);
  const target = buildBackendUrl(pathSegments, url.search);

  // Copiamos headers, eliminando hop-by-hop y accept-encoding (evita líos con compresión)
  const headers = new Headers();
  for (const [k, v] of req.headers.entries()) {
    const key = k.toLowerCase();
    if (HOP_BY_HOP.has(key)) continue;
    if (key === "accept-encoding") continue;
    headers.set(k, v);
  }

  const init: RequestInit = {
    method: req.method,
    headers,
    body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
    redirect: "follow",
  };

  try {
    const res = await fetch(target, init);

    // Copiamos headers de respuesta, quitando content-length/encoding (proxy seguro)
    const outHeaders = new Headers(res.headers);
    outHeaders.delete("content-length");
    outHeaders.delete("content-encoding");

    return new Response(res.body, {
      status: res.status,
      headers: outHeaders,
    });
  } catch (err: any) {
    // En vez de 500 vacío, devolvemos 502 con contexto para depurar
    return Response.json(
      {
        error: "Bad Gateway",
        message: err?.message ?? String(err),
        target,
      },
      { status: 502 }
    );
  }
}

export async function GET(req: NextRequest, ctx: any) { return proxy(req, ctx); }
export async function POST(req: NextRequest, ctx: any) { return proxy(req, ctx); }
export async function PUT(req: NextRequest, ctx: any) { return proxy(req, ctx); }
export async function PATCH(req: NextRequest, ctx: any) { return proxy(req, ctx); }
export async function DELETE(req: NextRequest, ctx: any) { return proxy(req, ctx); }
