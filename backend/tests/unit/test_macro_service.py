"""MacroService tests."""
from unittest.mock import patch

from application.services.macro_service import MacroService


def test_macro_payload_includes_universe_size():
    with patch("application.services.macro_service.macro.macro_payload",
               return_value={"snapshot": [], "news": [], "bias": {}, "mode": "cache"}):
        payload = MacroService().macro_payload()
    assert payload["universe_size"] > 0
