import datetime as dt
import unittest

from hotel_monitor.config import LOGOS_PROFILE
from hotel_monitor.models import HotelOffer
from hotel_monitor.services import MarketService, SimilarityService, parse_price


class PriceParsingTests(unittest.TestCase):
    def test_parses_polish_price(self) -> None:
        self.assertEqual(parse_price("1 234,50 PLN"), 1234.5)

    def test_parses_international_price(self) -> None:
        self.assertEqual(parse_price("PLN 1,234.50"), 1234.5)

    def test_parses_nested_price(self) -> None:
        self.assertEqual(parse_price({"value": 999}), 999.0)


class FallbackTests(unittest.TestCase):
    def test_demo_snapshot_respects_stay_length(self) -> None:
        snapshot = MarketService(None).get_snapshot(dt.date(2026, 10, 1), dt.date(2026, 10, 3))

        self.assertFalse(snapshot.is_live)
        self.assertEqual(snapshot.logos_total_price, 840.0)
        self.assertEqual(len(snapshot.offers), 10)

    def test_local_similarity_is_bounded(self) -> None:
        competitor = HotelOffer(
            "Hotel Test 3* SPA",
            nightly_price=400,
            total_price=800,
            description="Hotel w centrum ze strefą SPA",
        )

        result = SimilarityService(None).compare(LOGOS_PROFILE, competitor)

        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)


if __name__ == "__main__":
    unittest.main()
