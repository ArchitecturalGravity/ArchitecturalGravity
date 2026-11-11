"""One-shot mock-model worker; JSON framing is independent of any provider CLI."""
from __future__ import annotations
import base64
import json
import sys
from .catalog import runtime
from AgMark.shared.mock_model.protocol import ProtocolInferenceError


def main():
    try:
        raw = sys.stdin.buffer.read()
        envelope = json.loads(raw)
        if set(envelope) != {"protocol", "model_id", "invocation_id", "prompt_base64", "input_base64"}:
            raise ValueError("invalid fields")
        if envelope["protocol"] != "agmark.mock-worker/1":
            raise ValueError("unsupported protocol")
        # Validate exact framed payload, then supply the complete canonical
        # request to the deterministic model. No provider prompt format exists.
        for field in ("prompt_base64", "input_base64"):
            base64.b64decode(envelope[field], validate=True)
        def partial(stdout, stderr):
            sys.stdout.buffer.write(stdout); sys.stdout.buffer.flush()
            sys.stderr.buffer.write(stderr); sys.stderr.buffer.flush()
        result = runtime().infer(model_id=envelope["model_id"], request_bytes=raw,
            invocation_id=envelope["invocation_id"], partial_output_sink=partial)
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        return result.exit_code
    except ProtocolInferenceError as exc:
        sys.stderr.write("mock_inference_failed:" + exc.code + "\n")
        return 2
    except (ValueError, TypeError, KeyError):
        sys.stderr.write("mock_request_invalid\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
