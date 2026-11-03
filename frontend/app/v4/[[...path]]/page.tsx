import { notFound } from 'next/navigation';
import { Demo } from '../../../components/v4/demo';

// Read only server-owned public origin configuration, using the same restrictions as the M3 entry.
function apiOrigin(): string | null {
  const origin = process.env.COMMERCEOPS_API_ORIGIN;
  const localHttp = process.env.COMMERCEOPS_WEB_TRANSPORT === 'local_http';
  try {
    const url = new URL(origin ?? '');
    if (url.origin !== origin || url.username || url.password) return null;
    if (url.protocol === 'https:') return url.origin;
    if (localHttp && url.protocol === 'http:' && ['127.0.0.1','localhost','[::1]'].includes(url.hostname)) return url.origin;
  } catch { /* Missing or invalid configuration has no network fallback. */ }
  return null;
}
export default async function Page({params}: {params: Promise<{path?: string[]}>}) {
  const path = (await params).path ?? [];
  if (!['', 'demo', 'settings/demo'].includes(path.join('/'))) notFound();
  return <Demo origin={apiOrigin()} />;
}
