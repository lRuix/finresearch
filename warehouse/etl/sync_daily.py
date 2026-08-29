"""Daily real-data warehouse sync entrypoint for cron or desktop automation."""
from __future__ import annotations

import sys

from etl.sources import registry
from etl.universe import static_universe_for


def main() -> int:
    original_discover = registry.discover_instruments

    def dynamic_or_static(market: str):
        try:
            rows = original_discover(market)
        except Exception:
            rows = []
        if rows:
            return rows
        return static_universe_for(market)

    registry.discover_instruments = dynamic_or_static
    try:
        from etl.sync_incremental import main as sync_main

        sync_main()
    except Exception:
        return 1
    finally:
        registry.discover_instruments = original_discover
    return 0


if __name__ == "__main__":
    sys.exit(main())
