import { NextRequest, NextResponse } from "next/server";

const endpoint = "https://aidevboard.com/api/v1/jobs";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q") ?? "AI engineer";
  const remote = request.nextUrl.searchParams.get("remote") === "true";
  const level = request.nextUrl.searchParams.get("level") ?? "";
  const params = new URLSearchParams({ q: query, limit: "30" });
  if (remote) params.set("workplace", "remote");
  if (level && level !== "student") params.set("level", level === "entry" ? "junior" : level);
  try {
    const response = await fetch(`${endpoint}?${params}`, { next: { revalidate: 900 }, headers: { "User-Agent": "RoleRadar/0.2" } });
    if (!response.ok) throw new Error(`Source returned ${response.status}`);
    return NextResponse.json(await response.json());
  } catch {
    return NextResponse.json({ jobs: [], error: "The live job source is currently unavailable. Please try again shortly." }, { status: 503 });
  }
}
