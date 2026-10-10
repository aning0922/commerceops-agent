# 项目本地字体

冻结 Source Sans Pro + Noto Sans SC 语义采用项目本地 Fontsource 包，不安装系统字体，不发站外字体请求。

| 包 | 固定版本 | 本批加载 | 许可证 |
|---|---|---|---|
| `@fontsource/source-sans-pro` | 5.3.0 | 400/600 的包内 CSS/WOFF2 | OFL-1.1 |
| `@fontsource-variable/noto-sans-sc` | 5.3.0 | wght 轴，页面400/600；CSS family名 `Noto Sans SC Variable` 是同Noto Sans SC字体的变量形式 | OFL-1.1 |

原始许可证随包保留，并复制到交付服务静态资产 [Source Sans Pro](public/fonts/source-sans-pro-LICENSE.txt) / [Noto Sans SC](public/fonts/noto-sans-sc-LICENSE.txt)。两者许可证 SHA256 均为 `18aabf190848725e2576eefb5c29ba06aac1029d02132252a7f312eac2e50cf3`。

依据：[Fontsource 自托管安装](https://fontsource.org/docs/getting-started/install)、[Noto Sans SC 包](https://fontsource.org/fonts/noto-sans-sc/use)、[Noto 官方许可证说明](https://github.com/notofonts/noto-docs/blob/main/docs/website/use.md)。不宣称全平台字体验收；实际 OS/字体 glyph 记录由 Web 定向测试生成至 `evidence/b01/cjk-font-<platform>.json`，Linux下载阻断另留 `linux-download.json`。不以 macOS fallback 或 fc-match 冒称 Linux 浏览器通过。
