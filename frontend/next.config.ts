import type { NextConfig } from "next";
// Public HTTP header names and values, not credentials.
const responseHeaders = new Map([
  ["X-Content-Type-Options", "nosniff"],
  ["Referrer-Policy", "same-origin"],
  ["X-Frame-Options", "DENY"],
  ["Cache-Control", "no-store"],
]);
const config: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: Array.from(responseHeaders, ([name, headerValue]) => ({
          key: name,
          value: headerValue,
        })),
      },
    ];
  },
};
export default config;
