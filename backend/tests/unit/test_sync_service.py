"""SyncService tests with in-memory repository and fake datasource."""
from domain.models import KlineRow
from application.services.sync_service import SyncService


class FakeRepository:
    def __init__(self):
        self.upserted = []
        self.watermarks = {}

    def get_watermark(self, market, symbol, period):
        return self.watermarks.get((market, symbol, period))

    def set_watermark(self, market, symbol, period, as_of):
        self.watermarks[(market, symbol, period)] = as_of

    def upsert_klines(self, market, symbol, period, rows):
        self.upserted.append((market, symbol, period, rows))


class FakeDatasource:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error

    def get_klines_with_source(self, market, symbol, period,
                               start=None, end=None, limit=180,
                               prefer_real: bool = True):
        if self.error:
            raise self.error
        return self.rows, "live"

    def get_klines(self, market, symbol, period, start=None, end=None, limit=180,
                   prefer_real: bool = True):
        rows, _ = self.get_klines_with_source(
            market, symbol, period, start, end, limit, prefer_real,
        )
        return rows


def test_sync_writes_rows_and_advances_watermark():
    repo = FakeRepository()
    rows = [
        KlineRow("2026-08-22", 1, 2, 0.5, 1.5, 100),
        KlineRow("2026-08-23", 1.5, 2.5, 1.2, 2.2, 120),
    ]
    service = SyncService(repo, FakeDatasource(rows=rows))
    result_rows, source = service.sync("us", "AAPL", "d")
    assert result_rows == rows
    assert source == "live"
    assert repo.upserted == [("us", "AAPL", "d", rows)]
    assert repo.watermarks[("us", "AAPL", "d")] == "2026-08-23"


def test_sync_does_not_advance_on_failure():
    repo = FakeRepository()
    service = SyncService(repo, FakeDatasource(error=RuntimeError("upstream down")))
    try:
        service.sync("us", "AAPL", "d")
    except RuntimeError:
        pass
    assert repo.upserted == []
    assert repo.watermarks == {}


def test_sync_uses_existing_watermark_as_start():
    repo = FakeRepository()
    repo.watermarks[("us", "AAPL", "d")] = "2026-08-22"
    captured = {}

    class RecordingDatasource:
        def get_klines_with_source(self, market, symbol, period,
                                   start=None, end=None, limit=180,
                                   prefer_real: bool = True):
            captured["start"] = start
            return [], "mock"

        def get_klines(self, market, symbol, period, start=None, end=None, limit=180,
                       prefer_real: bool = True):
            rows, source = self.get_klines_with_source(
                market, symbol, period, start, end, limit, prefer_real,
            )
            return rows

    SyncService(repo, RecordingDatasource()).sync("us", "AAPL", "d")
    assert captured["start"] == "2026-08-22"


def test_sync_short_circuits_when_watermark_covers_end():
    repo = FakeRepository()
    repo.watermarks[("us", "AAPL", "d")] = "2026-08-23"
    called = {"count": 0}

    class RecordingDatasource:
        def get_klines_with_source(self, market, symbol, period,
                                   start=None, end=None, limit=180,
                                   prefer_real: bool = True):
            called["count"] += 1
            return [], "live"

        def get_klines(self, market, symbol, period, start=None, end=None, limit=180,
                       prefer_real: bool = True):
            rows, source = self.get_klines_with_source(
                market, symbol, period, start, end, limit, prefer_real,
            )
            return rows

    rows, source = SyncService(repo, RecordingDatasource()).sync(
        "us", "AAPL", "d", end="2026-08-23",
    )
    assert rows == []
    assert source == "local"
    assert called["count"] == 0


def test_sync_empty_rows_does_not_advance():
    repo = FakeRepository()
    service = SyncService(repo, FakeDatasource(rows=[]))
    rows, _ = service.sync("us", "AAPL", "d")
    assert rows == []
    assert repo.upserted == []
    assert repo.watermarks == {}


def test_sync_keeps_caller_start_when_later_than_watermark():
    repo = FakeRepository()
    repo.watermarks[("us", "AAPL", "d")] = "2026-08-22"
    captured = {}

    class RecordingDatasource:
        def get_klines_with_source(self, market, symbol, period,
                                   start=None, end=None, limit=180,
                                   prefer_real: bool = True):
            captured["start"] = start
            return [], "mock"

        def get_klines(self, market, symbol, period, start=None, end=None, limit=180,
                       prefer_real: bool = True):
            rows, source = self.get_klines_with_source(
                market, symbol, period, start, end, limit, prefer_real,
            )
            return rows

    SyncService(repo, RecordingDatasource()).sync("us", "AAPL", "d", start="2026-08-25")
    assert captured["start"] == "2026-08-25"


def test_sync_forwards_prefer_real_to_datasource():
    repo = FakeRepository()
    captured = {}

    class RecordingDatasource:
        def get_klines_with_source(self, market, symbol, period,
                                   start=None, end=None, limit=180,
                                   prefer_real: bool = True):
            captured["prefer_real"] = prefer_real
            return [], "mock"

        def get_klines(self, market, symbol, period, start=None, end=None,
                       limit=180, prefer_real: bool = True):
            rows, source = self.get_klines_with_source(
                market, symbol, period, start, end, limit, prefer_real,
            )
            return rows

    SyncService(repo, RecordingDatasource()).sync(
        "us", "AAPL", "d", prefer_real=False,
    )
    assert captured["prefer_real"] is False
