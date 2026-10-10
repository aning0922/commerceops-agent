"use client";
// Reuses the production page loader with a memory-only adapter. The server page
// invokes this wrapper only in explicit Mock mode, never in the live branch.
import { useCallback } from "react";
import { LiveConsole } from "./live-console";
import { createOfflineItemClient, offlineId } from "../lib/b04-offline-source";
import type { OfflineScenario } from "../lib/b04-offline-source";
export function B04WiringPreview({
  path,
  scenario,
}: {
  path: string;
  scenario: OfflineScenario;
}) {
  const selected = Array.from(
    { length: 20 },
    (_, n) => `/replenishment-items/${offlineId(n + 1)}`,
  ).indexOf(path);
  const factory = useCallback(
    (invalidate: () => void) =>
      createOfflineItemClient(
        scenario,
        invalidate,
        undefined,
        Math.max(1, selected + 1),
      ),
    [scenario, selected],
  );
  return (
    <LiveConsole
      path={path}
      query={{}}
      origin={null}
      localHttp={false}
      fixtureMode
      fixtureClient={factory}
    />
  );
}
