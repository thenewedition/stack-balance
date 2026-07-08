"use strict";

async function request(path, options = {}) {
  const response = await fetch("/api" + path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

const json = (method) => (path, body) =>
  request(path, { method, headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(body) });

export const api = {
  get: (path) => request(path),
  post: json("POST"),
  put: json("PUT"),
  patch: json("PATCH"),
  del: (path) => request(path, { method: "DELETE" }),
  /** multipart upload; fields is a plain object, file is a File/Blob.
   *  Retries once on a transport-level failure (TypeError/NetworkError) —
   *  safe here because import dedupes by content hash and restore replaces
   *  everything, so a duplicate delivery cannot double-apply. */
  upload: async (path, fields, file, filename) => {
    const form = new FormData();
    for (const [key, value] of Object.entries(fields)) form.append(key, value);
    form.append("file", file, filename ?? file.name ?? "upload");
    try {
      return await request(path, { method: "POST", body: form });
    } catch (error) {
      if (!(error instanceof TypeError)) throw error;
      await new Promise((resolve) => setTimeout(resolve, 400));
      return request(path, { method: "POST", body: form });
    }
  },
};
