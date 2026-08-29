"""Daily real-data warehouse sync entrypoint for cron or desktop automation."""
from __future__ import annotations

import sys

from etl.sources import registry
from etl.universe import static_universe_for


def main() -> int:
    original_discover = registry.discover_instruments

    def static_or_dynamic(market: str):
        static = static_universe_for(market)
        if static:
            return static
        try:
            return original_discover(market)
        except Exception:
            return []

    registry.discover_instruments = static_or_dynamic
    try:
        from etl.sync_incremental import main as sync_main

        sync_main()
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
