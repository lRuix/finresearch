"""Service container wiring smoke test."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from application.config import AppConfig
from app import build_container


def test_container_wires_all_services():
    datasource = MagicMock()
    container = build_container(
        AppConfig(db_path=Path(tempfile.mkdtemp()) / "test.db"),
        datasource=datasource,
    )
    assert container.analysis_service is not None
    assert container.screening_service is not None
    assert container.recommendation_service is not None
    assert container.comparison_service is not None
    assert container.sync_service is not None
    assert container.catalog_service is not None
    assert container.search_service is not None
    assert container.macro_service is not None
    assert container.macro_service.macro_payload(False)["universe_size"] > 0
