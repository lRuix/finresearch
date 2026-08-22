"""SearchService tests."""
from unittest.mock import patch

from application.services.search_service import SearchService


def test_search_delegates_to_core_search():
    with patch("application.services.search_service._search",
               return_value={"query": "AAPL", "items": [], "total": 0}) as mock_search:
        result = SearchService().search("AAPL")
    assert result["total"] == 0
    mock_search.assert_called_once_with("AAPL", 10)
