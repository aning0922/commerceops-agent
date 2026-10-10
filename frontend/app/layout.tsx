import "@fontsource/source-sans-pro/400.css";
import "@fontsource/source-sans-pro/600.css";
import "@fontsource-variable/noto-sans-sc/wght.css";
import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "CommerceOps · 运营协作工作台",
  description: "冻结 M1 操作台 · 明确离线 Mock 样例",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
