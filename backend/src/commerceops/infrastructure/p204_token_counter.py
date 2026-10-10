"""固定官方V4.1纯文本编码；本地计数加保守余量，不称API实际计量。"""

import gzip
import hashlib
import json
from pathlib import Path

from tokenizers import Tokenizer

from commerceops.application.model_explanation.contracts import MODEL, Message, TokenCount

REVISION = "2cba9e42aa026125f3ed06c6d98c1db82f7ca027"
SOURCE_DIGEST = "c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b"
PACK_DIGEST = "b560c0d1f2d08871d9588b054d1e4f63338da5007da5fcccdf9bbdaff01f677c"
COUNT_VERSION = "dsv41-2cba9e42-chat-byte4096-margin1024-v1"
MAX_VISIBLE_BYTES = 4096
API_MARGIN = 1024
BOS = "<｜begin▁of▁sentence｜>"
SYSTEM_MARKER = "<｜System｜>"
USER_MARKER = "<｜User｜>"
ASSISTANT = "<｜Assistant｜>"
END_THINK = "</think>"


class VerifiedTextCounter:
    def __init__(self) -> None:
        packed = (Path(__file__).parent / "token_assets/dsv41.json.gz").read_bytes()
        if hashlib.sha256(packed).hexdigest() != PACK_DIGEST:
            raise ValueError("TOKENIZER_ASSET_INVALID")
        raw = gzip.decompress(packed)
        if len(raw) != 6367257 or hashlib.sha256(raw).hexdigest() != SOURCE_DIGEST:
            raise ValueError("TOKENIZER_ASSET_INVALID")
        spec = json.loads(raw)
        if (
            spec["model"]["type"] != "BPE"
            or spec["normalizer"] != {"type": "Sequence", "normalizers": []}
            or spec["post_processor"]["type"] != "ByteLevel"
        ):
            raise ValueError("TOKENIZER_ASSET_INVALID")
        self._literals = tuple(token["content"] for token in spec["added_tokens"])
        if not all(type(literal) is str and literal for literal in self._literals):
            raise ValueError("TOKENIZER_ASSET_INVALID")
        self._tokenizer = Tokenizer.from_str(raw.decode())

    def render(self, messages: tuple[Message, ...]) -> str:
        if type(messages) is not tuple or len(messages) != 2:
            raise ValueError("TOKENIZER_PROFILE_DENIED")
        if tuple(m.role for m in messages) != ("system", "user"):
            raise ValueError("TOKENIZER_PROFILE_DENIED")
        for m in messages:
            if type(m) is not Message or type(m.content) is not str or not m.content:
                raise ValueError("TOKENIZER_PROFILE_DENIED")
            if len(m.content) > MAX_VISIBLE_BYTES:
                raise ValueError("TOKENIZER_PROFILE_DENIED")
            if any(literal in m.content for literal in self._literals):
                raise ValueError("TOKENIZER_CONTROL_LITERAL")
        # 官方encode_messages(chat)的system+user严格子集，无tool/media/context/history。
        rendered = (
            BOS
            + SYSTEM_MARKER
            + messages[0].content
            + USER_MARKER
            + messages[1].content
            + ASSISTANT
            + END_THINK
        )
        if len(rendered.encode("utf8")) > MAX_VISIBLE_BYTES:
            raise ValueError("TOKENIZER_PROFILE_DENIED")
        return rendered

    def count(self, messages: tuple[Message, ...], *, model: str) -> TokenCount:
        if model != MODEL:
            raise ValueError("TOKENIZER_PROFILE_DENIED")
        rendered = self.render(messages)
        measured = len(self._tokenizer.encode_batch([rendered], add_special_tokens=False)[0].ids)
        visible_bound = len(rendered.encode("utf8"))
        if not 1 <= measured <= visible_bound:
            raise ValueError("TOKENIZER_BOUND_INVALID")
        # 字节BPE可见prompt上界+明确API差异余量；metadata不冒充实际prompt_tokens。
        return TokenCount(visible_bound + API_MARGIN, MODEL, COUNT_VERSION, "verified_tokenizer")
