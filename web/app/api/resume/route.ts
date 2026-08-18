import { NextRequest, NextResponse } from "next/server";
import { PDFParse } from "pdf-parse";
import { execFile } from "node:child_process";
import { access, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";

const allowedHosts = new Set(["github.com", "raw.githubusercontent.com", "drive.google.com", "docs.google.com"]);
const maxCharacters = 2_000_000;
const maxFileBytes = 8 * 1024 * 1024;
const execFileAsync = promisify(execFile);

PDFParse.setWorker("https://cdn.jsdelivr.net/npm/pdf-parse@2.4.5/dist/pdf-parse/web/pdf.worker.min.mjs");

function trimText(text: string) {
  return text.replace(/\u0000/g, "").replace(/\s+\n/g, "\n").trim().slice(0, maxCharacters);
}

async function extractPdfText(buffer: ArrayBuffer) {
  try {
    const parser = new PDFParse({ data: Buffer.from(buffer) });
    try {
      const parsed = await parser.getText();
      return trimText(parsed.text ?? "");
    } finally {
      await parser.destroy();
    }
  } catch {
    return extractPdfTextWithPython(buffer);
  }
}

async function extractPdfTextWithPython(buffer: ArrayBuffer) {
  const pythonPath = resolve(process.cwd(), "..", ".venv", "bin", "python");
  await access(pythonPath);
  const tempPath = join(tmpdir(), `roleradar-${Date.now()}.pdf`);
  await writeFile(tempPath, Buffer.from(buffer));
  try {
    const { stdout } = await execFileAsync(
      pythonPath,
      [
        "-c",
        [
          "from pathlib import Path",
          "from pypdf import PdfReader",
          "import sys",
          "path = Path(sys.argv[1])",
          "text = '\\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)",
          "print(text)",
        ].join("; "),
        tempPath,
      ],
      { maxBuffer: 10 * 1024 * 1024 },
    );
    return trimText(stdout);
  } finally {
    await rm(tempPath, { force: true });
  }
}

async function extractFileText(file: File) {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  return isPdf ? extractPdfText(await file.arrayBuffer()) : trimText(await file.text());
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "Choose a resume file to upload." }, { status: 400 });
    }
    if (file.size === 0) {
      return NextResponse.json({ error: "That file is empty." }, { status: 400 });
    }
    if (file.size > maxFileBytes) {
      return NextResponse.json({ error: "Use a resume smaller than 8 MB." }, { status: 400 });
    }
    const text = await extractFileText(file);
    if (!text) {
      return NextResponse.json({ error: "Could not extract readable text from that file. Try a text-based PDF, TXT, or Markdown resume." }, { status: 400 });
    }
    return NextResponse.json({ text, source: file.name });
  } catch {
    return NextResponse.json({ error: "Resume upload failed. Try a text-based PDF, TXT, or Markdown file." }, { status: 500 });
  }
}

export async function GET(request: NextRequest) {
  const value = request.nextUrl.searchParams.get("url");
  if (!value) return NextResponse.json({ error: "A resume URL is required." }, { status: 400 });
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return NextResponse.json({ error: "Enter a valid HTTPS URL." }, { status: 400 });
  }
  if (url.protocol !== "https:" || !allowedHosts.has(url.hostname)) {
    return NextResponse.json({ error: "For safety, use a GitHub or Google Drive HTTPS resume link, or upload a file." }, { status: 400 });
  }
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
    const body = trimText(await response.text());
    if (!body) {
      return NextResponse.json({ error: "That link did not return readable resume text." }, { status: 400 });
    }
    return NextResponse.json({ text: body, source: "shared resume link" });
  } catch {
    return NextResponse.json({ error: "Could not retrieve that resume link." }, { status: 502 });
  }
}
