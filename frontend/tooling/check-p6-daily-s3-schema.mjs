import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
for (const [file, digest] of [
  ["p6-daily-s3-read-schema.generated.json", "fe108320d164496558f73fbbe0698c9c9ae9800182db82d03fce51da5a12954c"],
  ["p6-daily-s3-openapi.generated.json", "8ea4454551e3fc17f00564de2a09143771742988458561c5a6a6b2ec16d245fc"],
]) {
  const contents = await readFile(new URL(`../lib/${file}`, import.meta.url));
  if (createHash("sha256").update(contents).digest("hex") !== digest) throw new Error(`S3 frozen asset differs: ${file}`);
}
console.log("Daily S3 read schema and OpenAPI match frozen 32dd7c candidate");
