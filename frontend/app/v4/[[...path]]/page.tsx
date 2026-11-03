import { notFound } from 'next/navigation';
import { Demo } from '../../../components/v4/demo';

import {approvedApiOrigin} from '../../../lib/v4-origin.mjs';

export default async function Page({params}: {params: Promise<{path?: string[]}>}) {
  const path = (await params).path ?? [];
  if (!['', 'demo', 'settings/demo'].includes(path.join('/'))) notFound();
  return <Demo origin={approvedApiOrigin(process.env.COMMERCEOPS_API_ORIGIN, process.env.COMMERCEOPS_WEB_TRANSPORT === 'local_http')} />;
}
