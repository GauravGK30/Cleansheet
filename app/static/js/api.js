// Thin wrapper around fetch: JSON in, JSON out, and errors that already carry a message fit to show to people.

export class ApiError extends Error {
  constructor(message, status = 0, code = "") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(method, url, { json, body, headers = {} } = {}) {
  const options = { method, headers: { ...headers }, credentials: "same-origin" };
  if (json !== undefined) {
    options.body = JSON.stringify(json);
    options.headers["Content-Type"] = "application/json";
  } else if (body !== undefined) {
    options.body = body;
  }
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new ApiError("Could not reach the CleanSheet server. Check that it is still running and try again.");
  }
  return response;
}

async function readJson(response) {
  const type = response.headers.get("content-type") || "";
  const data = type.includes("json") ? await response.json().catch(() => null) : null;
  if (!response.ok) {
    throw new ApiError((data && data.error) || "Something went wrong. Please try again.",
      response.status, (data && data.code) || "");
  }
  return data;
}

export const api = {
  get: async (url) => readJson(await request("GET", url)),
  post: async (url, json = {}) => readJson(await request("POST", url, { json })),
  async upload(file) {
    const response = await request("POST", "/api/upload", {
      body: file,
      headers: { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) },
    });
    return readJson(response);
  },
  async download(url) {
    const response = await request("GET", url);
    if (!response.ok) await readJson(response);            // throws with the server's message
    const disposition = response.headers.get("content-disposition") || "";
    const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    const plain = /filename="([^"]+)"/i.exec(disposition);
    const filename = star ? decodeURIComponent(star[1]) : plain ? plain[1] : "cleaned-data";
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
    return filename;
  },
};
