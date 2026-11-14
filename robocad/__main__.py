"""Entry point for ``python -m robocad``."""
from __future__ import annotations

import sys


def _dispatch(argv: list[str]) -> int:
    if not argv or argv[0] in ("start", "launch"):
        from robocad.launcher import main as launcher_main
        return launcher_main(argv[1:] if argv else None)
    if argv[0] in ("health", "check"):
        from robocad.health import main as health_main
        return health_main()
    if argv[0] == "demo":
        from robocad.demo import main as demo_main
        return demo_main(argv[1:])
    if argv[0] == "joints":
        from robocad.joints_cli import main as joints_main
        return joints_main(argv[1:])
    if argv[0] == "twin":
        from robocad.twin_cli import main as twin_main
        return twin_main(argv[1:])
    print(f"Unknown robocad command: {argv[0]}")
    print("Usage: python -m robocad [start|health|joints|demo|twin]")
    return 1


def main() -> int:
    return _dispatch(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
