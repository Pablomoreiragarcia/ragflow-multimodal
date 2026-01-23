function normalize(path: string) {
  // Evita el 308 de Next por /api/.../
  return path.endsWith("/") ? path.slice(0, -1) : path;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(normalize(path), { credentials: "include" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost<TBody, TResp>(path: string, body: TBody): Promise<TResp> {
  const res = await fetch(normalize(path), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  // a veces DRF devuelve Conversation (sin messages). Para UI nos da igual: refetch luego.
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : ({} as TResp);
}

export async function apiPostForm<TResp>(path: string, form: FormData): Promise<TResp> {
  const res = await fetch(path, {
    method: "POST",
    body: form,
    credentials: "include",
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(txt || `HTTP ${res.status}`);
  }
  return res.json() as Promise<TResp>;
}