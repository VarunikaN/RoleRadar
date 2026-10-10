import { NextRequest, NextResponse } from "next/server";
import { PDFParse } from "pdf-parse";
import {
  MAX_FILE_BYTES,
  MAX_LINK_BYTES,
  checkLinkContentType,
  checkResumeText,
  clientKey,
  fileKind,
  hasPdfMagic,
  rateLimited,
  readCapped,
  validateResumeUrl,
  ALLOWED_HOSTS,
} from "../../../lib/guards";
import { USER_AGENT } from "../../../lib/sources";

const MAX_REDIRECTS = 3;

PDFParse.setWorker("https://cdn.jsdelivr.net/npm/pdf-parse@2.4.5/dist/pdf-parse/web/pdf.worker.min.mjs");

const fail = (error: string, status: number) => NextResponse.json({ error }, { status });
const tooMany = () => fail("Too many requests. Wait a minute and try again.", 429);

async function extractPdfText(buffer: ArrayBuffer): Promise<string> {
  const parser = new PDFParse({ data: Buffer.from(buffer) });
  try {
    return (await parser.getText()).text ?? "";
  } finally {
    await parser.destroy();
  }
}

export async function POST(request: NextRequest) {
  if (rateLimited(clientKey(request.headers, "resume-upload"), 20)) return tooMany();
  const declared = Number(request.headers.get("content-length"));
  if (declared > MAX_FILE_BYTES + 100_000) return fail("Use a resume smaller than 8 MB.", 413);
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return fail("That upload could not be read. Choose the file again.", 400);
  }
  const file = formData.get("file");
  if (!(file instanceof File)) return fail("Choose a resume file to upload.", 400);
  if (file.size === 0) return fail("That file is empty.", 400);
  if (file.size > MAX_FILE_BYTES) return fail("Use a resume smaller than 8 MB.", 413);
  const kind = fileKind(file.name, file.type);
  if (!kind) return fail("Unsupported file type. Use PDF, TXT, or Markdown.", 415);

  let raw: string;
  if (kind === "pdf") {
    const buffer = await file.arrayBuffer();
    if (!hasPdfMagic(new Uint8Array(buffer))) {
      return fail("That file is not a real PDF. Export a text-based PDF or upload TXT/Markdown.", 422);
    }
    try {
      raw = await extractPdfText(buffer);
    } catch {
      return fail("I could not read that PDF. It may be corrupted, password-protected, or scanned. Export a text-based PDF instead.", 422);
    }
    if (!raw.trim()) {
      return fail("That PDF does not contain readable text. It may be a scan. Export a text-based PDF instead.", 422);
    }
  } else {
    raw = await file.text();
  }
  const checked = checkResumeText(raw);
  if (!checked.ok) return fail(checked.error, checked.status);
  return NextResponse.json({ text: checked.value, source: file.name.slice(0, 120) });
}

async function fetchAllowed(start: URL): Promise<Response> {
  let url = start;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop += 1) {
    const response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(10_000), headers: { "User-Agent": USER_AGENT } });
    if (response.status < 300 || response.status >= 400) return response;
    const location = response.headers.get("location");
    if (!location) throw new Error("redirect without location");
    const next = new URL(location, url);
    if (next.protocol !== "https:" || !ALLOWED_HOSTS.has(next.hostname)) throw new Error("redirect to a disallowed host");
    url = next;
  }
  throw new Error("too many redirects");
}

export async function GET(request: NextRequest) {
  if (rateLimited(clientKey(request.headers, "resume-link"), 20)) return tooMany();
  const checked = validateResumeUrl(request.nextUrl.searchParams.get("url"));
  if (!checked.ok) return fail(checked.error, checked.status);
  let response: Response;
  try {
    response = await fetchAllowed(checked.value);
  } catch {
    return fail("Could not retrieve that resume link.", 502);
  }
  if (response.status === 404) return fail("That link was not found (HTTP 404).", 404);
  if (!response.ok) return fail(`That link returned HTTP ${response.status}.`, 502);
  const type = checkLinkContentType(response.headers.get("content-type"));
  if (!type.ok) return fail(type.error, type.status);
  const body = await readCapped(response, MAX_LINK_BYTES);
  if (!body.ok) return fail(body.error, body.status);
  const text = checkResumeText(new TextDecoder("utf-8", { fatal: false }).decode(body.value));
  if (!text.ok) return fail(text.error, text.status);
  return NextResponse.json({ text: text.value, source: "shared resume link" });
}
