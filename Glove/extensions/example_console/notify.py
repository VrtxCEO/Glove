import json
import sys


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("no payload", file=sys.stderr)
        return 2
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"invalid json: {exc}", file=sys.stderr)
        return 3
    print("[EXAMPLE EXTENSION]", envelope.get("subject", ""), envelope.get("message", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
