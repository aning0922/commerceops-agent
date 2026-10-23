// Native module wrapper for the existing owned Mock helper; one fixed test port.
import { startOwnedMock } from "../../../../frontend/tooling/owned-mock.mjs";
const stopped = new Promise((resolve) => process.once("SIGTERM", resolve));
const startedUtc = new Date().toISOString();
const expiresUtc = new Date(Date.now() + 30 * 60 * 1000).toISOString();
let expiryTimer;
const expired = new Promise((resolve) => {
  expiryTimer = setTimeout(resolve, Date.parse(expiresUtc) - Date.now());
});
const owned = await startOwnedMock("http://127.0.0.1:3496");
console.log(
  JSON.stringify({
    pid: owned.pid,
    buildId: owned.buildId,
    serviceId: owned.serviceId,
    startedUtc,
    expiresUtc,
  }),
);
try {
  await Promise.race([stopped, expired]);
} finally {
  clearTimeout(expiryTimer);
  await owned.close();
}
