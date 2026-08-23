const MAX_BODY_BYTES = 1_024;
const DEFAULT_API_URL = "http://127.0.0.1:8000";

function json(body: object, status: number): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function POST(request: Request): Promise<Response> {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  if (contentType !== "application/json") {
    return json({ detail: "Content type must be application/json." }, 415);
  }

  const body = await request.text();
  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    return json({ detail: "Request body is too large." }, 413);
  }

  const apiUrl = (process.env.FAIDA_API_URL ?? DEFAULT_API_URL).replace(/\/$/, "");
  try {
    const upstream = await fetch(`${apiUrl}/api/waitlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });

    if (upstream.ok) return json({ ok: true }, 202);
    if (upstream.status === 422) {
      return json({ detail: "Enter a valid email address." }, 422);
    }
    return json({ detail: "The waitlist is temporarily unavailable." }, 503);
  } catch {
    return json({ detail: "The waitlist is temporarily unavailable." }, 503);
  }
}
