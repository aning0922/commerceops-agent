import { notFound } from 'next/navigation';
import { Demo } from '../../../components/v4/demo';
import { resolveV41Route } from '../../../lib/v41-routes';

import {approvedApiOrigin} from '../../../lib/v4-origin.mjs';

export default async function Page({params}: {params: Promise<{path?: string[]}>}) {
  const path = (await params).path ?? [];
  const pathname = `/v4${path.length ? `/${path.join('/')}` : ''}`;
  if (!resolveV41Route(pathname)) notFound();
  return <Demo origin={approvedApiOrigin(process.env.COMMERCEOPS_API_ORIGIN, process.env.COMMERCEOPS_WEB_TRANSPORT === 'local_http')} />;
}
