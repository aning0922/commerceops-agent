// This handles public server configuration only, never a browser-provided origin.
export function approvedApiOrigin(origin, localHttp) {
  try {
    const url = new URL(origin ?? '');
    if (url.origin !== origin || url.username || url.password) return null;
    if (url.protocol === 'https:') return url.origin;
    if (localHttp && url.protocol === 'http:' && ['127.0.0.1','localhost','[::1]'].includes(url.hostname)) return url.origin;
  } catch { /* No fallback for missing or malformed configuration. */ }
  return null;
}
