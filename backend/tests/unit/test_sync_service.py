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
                               start=None, end=None, limit=180):
        if self.error:
            raise self.error
        return self.rows, "live"

    def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
        rows, _ = self.get_klines_with_source(market, symbol, period, start, end, limit)
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
                                   start=None, end=None, limit=180):
            captured["start"] = start
            return [], "mock"

        def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
            rows, source = self.get_klines_with_source(market, symbol, period, start, end, limit)
            return rows

    SyncService(repo, RecordingDatasource()).sync("us", "AAPL", "d")
    assert captured["start"] == "2026-08-22"
