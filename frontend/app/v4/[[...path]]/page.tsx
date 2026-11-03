import { notFound } from 'next/navigation';
import { Demo } from '../../../components/v4/demo';
export default async function Page({params}: {params: Promise<{path?: string[]}>}) {
  const path = (await params).path ?? [];
  if (!['', 'demo', 'settings/demo'].includes(path.join('/'))) notFound();
  return <Demo />;
}
