// Native module wrapper for the existing owned Mock helper; one fixed test port.
import { startOwnedMock } from "../../../../frontend/tooling/owned-mock.mjs";
const stopped = new Promise((resolve) => process.once("SIGTERM", resolve));
const owned = await startOwnedMock("http://127.0.0.1:3496");
console.log(
  JSON.stringify({
    pid: owned.pid,
    buildId: owned.buildId,
    serviceId: owned.serviceId,
  }),
);
try {
  await stopped;
} finally {
  await owned.close();
}
