export const MAX_FILE_BYTES = 8 * 1024 * 1024;
export const MAX_LINK_BYTES = 2_000_000;
export const MAX_QUERY_CHARS = 100;
export const MIN_RESUME_CHARS = 40;
export const MIN_RESUME_WORDS = 8;

const TEXT_SUFFIXES = [".txt", ".md", ".markdown", ".text"];
const LINK_TYPES = new Set(["text/plain", "text/markdown", "text/x-markdown", "application/markdown"]);
export const ALLOWED_HOSTS = new Set(["github.com", "raw.githubusercontent.com", "drive.google.com", "docs.google.com"]);
const LEVELS: Record<string, string> = { entry: "junior", junior: "junior", mid: "mid", senior: "senior" };

export type Checked<T> = { ok: true; value: T } | { ok: false; error: string; status: number };

const fail = (error: string, status = 400): { ok: false; error: string; status: number } => ({ ok: false, error, status });

export function checkResumeText(input: string): Checked<string> {
  const text = input.replace(/\u0000/g, "").replace(/\s+\n/g, "\n").trim().slice(0, 2_000_000);
  if (!text) return fail("That resume is empty.");
  let unprintable = 0;
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0;
    if ((code < 32 && char !== "\n" && char !== "\r" && char !== "\t") || char === "\uFFFD") unprintable += 1;
  }
  if (unprintable / text.length > 0.05) {
    return fail("That file doesn't look like text. Use a text-based PDF, TXT, or Markdown resume.", 422);
  }
  if (text.length < MIN_RESUME_CHARS || text.split(/\s+/).length < MIN_RESUME_WORDS) {
    return fail("That is too short to be a resume. Add a few lines of experience, projects, or skills.", 422);
  }
  const letters = (text.match(/\p{L}/gu) ?? []).length;
  if (letters / text.length < 0.5) return fail("That is mostly numbers or symbols, not resume text.", 422);
  return { ok: true, value: text };
}

export function fileKind(name: string, type: string): "pdf" | "text" | null {
  const lower = name.toLowerCase();
  if (type === "application/pdf" || lower.endsWith(".pdf")) return "pdf";
  if (TEXT_SUFFIXES.some((suffix) => lower.endsWith(suffix))) return "text";
  if (!type || type === "text/plain" || type === "text/markdown") return lower.includes(".") ? null : "text";
  return null;
}

export function hasPdfMagic(bytes: Uint8Array): boolean {
  const head = new TextDecoder("latin1").decode(bytes.slice(0, 1024));
  return head.includes("%PDF-");
}

export function toRawGithubUrl(url: URL): URL {
  const match = url.hostname === "github.com" ? url.pathname.match(/^\/([^/]+)\/([^/]+)\/blob\/(.+)$/) : null;
  return match ? new URL(`https://raw.githubusercontent.com/${match[1]}/${match[2]}/${match[3]}`) : url;
}

export function validateResumeUrl(value: string | null): Checked<URL> {
  if (!value || !value.trim()) return fail("A resume URL is required.");
  if (value.length > 2048) return fail("That link is too long.");
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    return fail("Enter a valid HTTPS URL.");
  }
  if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")) {
    return fail("Resume links must be plain HTTPS addresses.");
  }
  if (!ALLOWED_HOSTS.has(url.hostname)) {
    return fail("For safety, use a GitHub or Google Drive HTTPS resume link, or upload a file.");
  }
  return { ok: true, value: toRawGithubUrl(url) };
}

export function checkLinkContentType(header: string | null): Checked<string> {
  const type = (header ?? "").split(";")[0].trim().toLowerCase();
  if (type === "text/html") {
    return fail("That link returns a web page, not resume text. For GitHub use the Raw file link; Drive and Docs pages can't be read, so upload the file.", 422);
  }
  if (type === "application/pdf") return fail("Download the PDF and upload it; remote PDF links are not read.", 422);
  if (!LINK_TYPES.has(type)) return fail(`That link serves '${type || "unknown"}', not plain text or Markdown.`, 422);
  return { ok: true, value: type };
}

export async function readCapped(response: Response, maxBytes: number): Promise<Checked<Uint8Array>> {
  const declared = Number(response.headers.get("content-length"));
  if (declared > maxBytes) return fail("That link is larger than 2 MB. Use a smaller text resume.", 413);
  const reader = response.body?.getReader();
  if (!reader) return { ok: true, value: new Uint8Array() };
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > maxBytes) {
      await reader.cancel();
      return fail("That link is larger than 2 MB. Use a smaller text resume.", 413);
    }
    chunks.push(value);
  }
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return { ok: true, value: merged };
}

export function cleanQuery(value: string | null, fallback = ""): string {
  const cleaned = (value ?? "").split(/\s+/).filter(Boolean).join(" ").slice(0, MAX_QUERY_CHARS);
  return cleaned || fallback;
}

export function mapLevel(value: string | null): string | null {
  return LEVELS[(value ?? "").toLowerCase()] ?? null;
}

export function safeHttpUrl(value: unknown): string {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : "";
  } catch {
    return "";
  }
}

const hits = new Map<string, number[]>();

export function rateLimited(key: string, limit: number, windowMs = 60_000, now = Date.now()): boolean {
  const recent = (hits.get(key) ?? []).filter((time) => now - time < windowMs);
  if (recent.length >= limit) {
    hits.set(key, recent);
    return true;
  }
  recent.push(now);
  hits.set(key, recent);
  if (hits.size > 5000) hits.clear();
  return false;
}

export function clientKey(headers: Headers, scope: string): string {
  const forwarded = headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return `${scope}:${forwarded || headers.get("x-real-ip") || "local"}`;
}

export function resetRateLimits(): void {
  hits.clear();
}
