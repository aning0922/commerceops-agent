# P204 官方纯文本 tokenizer 固定资产

来源：DeepSeek 发布的 [DeepSeek-V4.1-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/tree/2cba9e42aa026125f3ed06c6d98c1db82f7ca027)。只包含 tokenizer 数据，不包含模型权重，不执行远端代码，runtime 不下载资产。MIT 许可见 LICENSE.deepseek。

| 资产 | 固定证据 |
| --- | --- |
| HF revision | `2cba9e42aa026125f3ed06c6d98c1db82f7ca027` |
| 原 tokenizer.json | 6367257 bytes；SHA256 `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b` |
| dsv41.json.gz | gzip mtime=0；1868514 bytes；SHA256 `b560c0d1f2d08871d9588b054d1e4f63338da5007da5fcccdf9bbdaff01f677c` |
| 官方 encoding/encoding.py | SHA256 `502bdaec8a3fd88ebc24c4721a7038fbe42f2063c664638127056107920035c1` |
| tokenizer runtime | tokenizers 0.23.2；上游 tag commit `88a4498ad4ea1a9487b0a9b0ff881383fd5a06a3` |

本地版本 `dsv41-2cba9e42-chat-byte4096-margin1024-v1` 只接受 system+user 两条纯文本消息。BOS、role 标记和 assistant/`</think>` 生成前缀按固定官方 chat 子集拼接；不支持工具、媒体、历史或自定义模板。拒绝输入中的全部官方 added-token literal；不通过清空 added_tokens 修补控制 token 的计数差异。

预检分别验证官方 BPE 实测 token 数和可见 UTF-8 字节上界，返回可见字节数+1024 的保守 API 差异余量。完整可见 framing 限制4096 bytes，所以本地 bound≤5120；不是 chars/4，也不是 API 实际 prompt_tokens。`encode_batch` 的上游 Rust Python binding 使用 detach 释放 GIL，避免计数线程阻塞 asyncio 的20秒截止。

服务端隐藏处理与官方 tokenizer 的差异未经实际调用验证，1024余量不构成无限 API 开销的数学证明。最终真实窗口必须核对 provider usage≤预检 bound、input≤8000、output≤800；任何缺失、越界、截断或未知计费信息停止阶段并保留完整预留。实际费用缺少账单证据时为NULL；价格估算独立标记，不能冒充实际费用。

固定 API model alias 及价格来源：[V4.1 release](https://api-docs.deepseek.com/news/news260910/)、[官方 pricing](https://api-docs.deepseek.com/quick_start/pricing/)。输入按 cache miss 峰值 US$0.30/M、输出 US$1.20/M；每次保留8000/800即US$0.00336，总调用≤10且USD预算≤0.10。价格版本 `ds-v41-peak-20261010` 须由总控在真实窗口前复核。
