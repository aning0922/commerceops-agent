"""官方 Penpot MCP 的 HTTP 验证客户端；不提供 MCP 服务或业务接口。"""

import argparse
import json
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, url_file: Path):
        self.url = url_file.read_text().strip()
        if not self.url.startswith("http://localhost:19001/mcp/stream?userToken="):
            raise ValueError("仅允许专用本机设计实例")
        self.session = None
        self.sequence = 0
        self.opener = urllib.request.build_opener(NoRedirect())
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "commerceops-design-probe", "version": "0.1.0"},
            },
        )
        self.request("notifications/initialized", {}, notification=True)

    def request(self, method, params, notification=False):
        self.sequence += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            body["id"] = self.sequence
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        # URL constructor above accepts only the dedicated loopback MCP endpoint.
        req = urllib.request.Request(self.url, json.dumps(body).encode(), headers)  # noqa: S310
        with self.opener.open(req, timeout=65) as response:
            self.session = response.headers.get("Mcp-Session-Id", self.session)
            if response.status == 202:
                return None
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                for raw in response:
                    line = raw.decode().strip()
                    if line.startswith("data: "):
                        value = json.loads(line[6:])
                        if value.get("id") == body.get("id"):
                            return value
                raise RuntimeError("MCP SSE 未返回匹配的响应")
            return json.loads(response.read())

    def call(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url-file", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client = Client(args.url_file)
    request = json.loads(args.request.read_text())
    result = client.request(request["method"], request.get("params", {}))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("MCP 响应已保存；凭据未回显")


if __name__ == "__main__":
    main()
