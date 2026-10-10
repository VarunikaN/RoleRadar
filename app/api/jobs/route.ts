import { NextRequest, NextResponse } from "next/server";
import { clientKey, cleanQuery, mapLevel, rateLimited } from "../../../lib/guards";
import { SourceError, fetchAll } from "../../../lib/sources";

const MAX_JOBS = 200;

export async function GET(request: NextRequest) {
  if (rateLimited(clientKey(request.headers, "jobs"), 30)) {
    return NextResponse.json({ jobs: [], error: "Too many requests. Wait a minute and try again." }, { status: 429 });
  }
  const query = cleanQuery(request.nextUrl.searchParams.get("q"));
  const remote = request.nextUrl.searchParams.get("remote") === "true";
  const level = mapLevel(request.nextUrl.searchParams.get("level"));
  const india = request.nextUrl.searchParams.get("india") === "true";
  try {
    const { jobs, warnings } = await fetchAll(query, remote, level, india);
    return NextResponse.json({ jobs: jobs.slice(0, MAX_JOBS), warnings, query });
  } catch (error) {
    if (error instanceof SourceError && error.status === 429) {
      return NextResponse.json({ jobs: [], error: "The job sources are rate limiting requests. Try again in a minute." }, { status: 429 });
    }
    return NextResponse.json({ jobs: [], error: "The live job sources are currently unavailable. Please try again shortly." }, { status: 503 });
  }
}
