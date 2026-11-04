// Forward one already-authorized request once, then discard the actual response.
// It never manufactures a response and never retries or follows redirects.
export async function dropActualResponse(route: { fetch: (options: { maxRetries: number; maxRedirects: number; timeout: number }) => Promise<{ status: () => number }>; abort: (code: "failed") => Promise<void> }, timeout: number): Promise<number> {
  let status = 0;
  try { status = (await route.fetch({ maxRetries: 0, maxRedirects: 0, timeout })).status(); }
  finally { await route.abort("failed"); }
  return status;
}
