"""MacroService tests."""
from unittest.mock import MagicMock

from application.services.macro_service import MacroService


def test_macro_payload_includes_universe_size():
    provider = MagicMock()
    provider.macro_payload.return_value = {
        "snapshot": [], "news": [], "bias": {}, "mode": "cache",
    }
    payload = MacroService(provider).macro_payload()
    assert payload["universe_size"] > 0
    provider.macro_payload.assert_called_once_with(False)
