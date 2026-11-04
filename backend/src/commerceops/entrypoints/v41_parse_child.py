"""Fixed one-shot pure parser child. The kernel timer is armed before application imports."""

import signal
import sys


def main() -> int:
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, 2.0)
    # No application imports, input reads or decompression occur before the native deadline.
    import json
    from uuid import UUID

    from commerceops.application.v41.imports import (
        FileRejected,
        decode_file,
        parse_file,
        quality_preview,
    )
    from commerceops.application.v41.parse_protocol import ParseInput, ParseResult
    from commerceops.domain.commerce_values import canonical_bytes

    try:
        if len(sys.argv) != 3 or sys.argv[1] != "--process-ref":
            raise ValueError("INVALID_REQUEST")
        if str(UUID(sys.argv[2])) != sys.argv[2]:
            raise ValueError("INVALID_REQUEST")
        raw = sys.stdin.buffer.read(3 * 1024 * 1024 + 1)
        if len(raw) > 3 * 1024 * 1024:
            raise ValueError("LIMIT_EXCEEDED")
        command = ParseInput.model_validate_json(raw)
        table = parse_file(decode_file(command.file_base64), command.format)
        quality = quality_preview(
            table, command.mapping, command.currency, frozenset(command.existing_skus)
        )
        result = ParseResult.from_quality(quality)
        output = canonical_bytes(result.model_dump(mode="json"))
        if len(output) > 2 * 1024 * 1024:
            raise ValueError("LIMIT_EXCEEDED")
        sys.stdout.buffer.write(output + b"\n")
        sys.stdout.buffer.flush()
        return 0
    except FileRejected:
        # Never echo parser input or exception chains to stdout/stderr.
        sys.stdout.write(json.dumps({"schema_version": "v41-parser-failure-1"}) + "\n")
        return 1
    except Exception:
        sys.stdout.write(json.dumps({"schema_version": "v41-parser-failure-1"}) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
