from __future__ import annotations

import datetime as dt
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from apify_client import ApifyClient
from groq import Groq

from hotel_monitor.config import APIFY_ACTORS, LOGOS_PROFILE
from hotel_monitor.models import AnalysisResult, HotelOffer, HotelProfile, MarketSnapshot

logger = logging.getLogger(__name__)


def parse_price(value: Any) -> float | None:
    """Normalize common numeric, text, and nested price formats returned by actors."""
    if isinstance(value, Mapping):
        value = value.get("value") or value.get("amount") or value.get("price")
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if not isinstance(value, str):
        return None

    cleaned = re.sub(r"[^\d,.-]", "", value.replace(" ", ""))
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        decimal_separator = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        cleaned = cleaned.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        parsed = float(cleaned)
        return parsed if parsed > 0 else None
    except ValueError:
        return None


class MarketService:
    def __init__(self, client: ApifyClient | None) -> None:
        self._client = client

    def get_snapshot(self, check_in: dt.date, check_out: dt.date) -> MarketSnapshot:
        nights = (check_out - check_in).days
        if nights <= 0:
            raise ValueError("Check-out must be later than check-in")

        warnings: list[str] = []
        if self._client is None:
            warnings.append("Brak APIFY_API_KEY — pokazujemy dane demonstracyjne.")
            return self._fallback_snapshot(nights, warnings)

        logos_total = self._fetch_logos_price(check_in, check_out)
        offers = self._fetch_market_offers(check_in, check_out, nights)
        if not offers:
            warnings.append(
                "Usługa cenowa jest chwilowo niedostępna — pokazujemy dane demonstracyjne."
            )
            return self._fallback_snapshot(nights, warnings)

        logos_offer = next((item for item in offers if "logos" in item.name.lower()), None)
        if logos_total is None and logos_offer:
            logos_total = logos_offer.total_price
            warnings.append("Cena Logos pochodzi z wyników wyszukiwania rynku.")
        elif logos_total is None:
            logos_total = 420.0 * nights
            warnings.append("Cena Logos jest szacunkiem — hotel nie zwrócił aktualnej oferty.")

        return MarketSnapshot(
            offers=offers,
            logos_nightly_price=round(logos_total / nights, 2),
            logos_total_price=round(logos_total, 2),
            is_live=True,
            warnings=warnings,
        )

    def _fetch_logos_price(self, check_in: dt.date, check_out: dt.date) -> float | None:
        run_input = self._base_input(check_in, check_out) | {
            "startUrls": [{"url": LOGOS_PROFILE.url}]
        }
        items = self._run_first_available(APIFY_ACTORS[:2], run_input)
        if not items:
            return None
        return self._item_price(items[0])

    def _fetch_market_offers(
        self, check_in: dt.date, check_out: dt.date, nights: int
    ) -> list[HotelOffer]:
        run_input = self._base_input(check_in, check_out) | {
            "search": "Zakopane",
            "searchLocation": "Zakopane",
            "maxItems": 20,
        }
        items = self._run_first_available(APIFY_ACTORS, run_input)
        return [offer for item in items if (offer := self._to_offer(item, nights))]

    def _run_first_available(
        self, actors: tuple[str, ...], run_input: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        for actor_id in actors:
            try:
                run = self._client.actor(actor_id).call(run_input=run_input)
                dataset_id = run.get("defaultDatasetId") if isinstance(run, Mapping) else None
                if not dataset_id:
                    continue
                return list(self._client.dataset(dataset_id).list_items().items)
            except Exception as exc:  # Third-party actor failures should not break the report.
                logger.warning("Apify actor %s failed: %s", actor_id, exc)
        return []

    @staticmethod
    def _base_input(check_in: dt.date, check_out: dt.date) -> dict[str, Any]:
        return {
            "checkIn": check_in.isoformat(),
            "checkOut": check_out.isoformat(),
            "adults": 2,
            "rooms": 1,
            "currency": "PLN",
        }

    @staticmethod
    def _item_price(item: Mapping[str, Any]) -> float | None:
        gross_price = item.get("grossPrice")
        return parse_price(item.get("price") or gross_price or item.get("price_raw"))

    @classmethod
    def _to_offer(cls, item: Mapping[str, Any], nights: int) -> HotelOffer | None:
        name = item.get("name") or item.get("title") or item.get("hotel_name")
        total_price = cls._item_price(item)
        if not name or total_price is None:
            return None

        rating = item.get("rating") or item.get("score") or "brak"
        stars = item.get("stars") or item.get("ratingText") or "brak danych"
        distance = (
            item.get("distance")
            or item.get("distanceFromCenter")
            or "nieznana odległość od centrum"
        )
        return HotelOffer(
            name=str(name),
            nightly_price=round(total_price / nights, 2),
            total_price=round(total_price, 2),
            description=f"Ocena: {rating}/10. Standard: {stars}. Lokalizacja: {distance}.",
        )

    @staticmethod
    def _fallback_snapshot(nights: int, warnings: list[str]) -> MarketSnapshot:
        raw_offers = (
            ("Hotel Logos Zakopane", 420, "Hotel 3*, SPA, centrum Zakopanego"),
            ("Hotel Czarny Potok 3*", 410, "Hotel 3*, basen, SPA, kameralny charakter"),
            ("Willa pod Skocznią", 230, "Pokoje gościnne, śniadania, bez strefy SPA"),
            ("Hotel Aquarion Family & SPA 4*", 670, "Hotel 4* połączony z Aquaparkiem"),
            ("Apartamenty Krupówki Premium", 460, "Apartament bez obsługi hotelowej i restauracji"),
            ("Hotel Gazdówka 3*", 380, "Regionalny hotel 3* na obrzeżach"),
            ("Grand Hotel Stamford Zakopane 5*", 910, "Hotel 5* ze strefą Wellness & SPA"),
            (
                "Hotel Belvedere Resort & SPA",
                590,
                "Resort z kompleksem basenowym i zapleczem konferencyjnym",
            ),
            ("Resort Nosalowy Dwór 4*", 620, "Nowoczesny resort pod Nosalem"),
            ("Aparthotel Giewont", 510, "Apartamenty w centrum ze strefą basenową"),
        )
        offers = [
            HotelOffer(name, float(price), float(price * nights), description)
            for name, price, description in raw_offers
        ]
        return MarketSnapshot(
            offers=offers,
            logos_nightly_price=420.0,
            logos_total_price=420.0 * nights,
            is_live=False,
            warnings=warnings,
        )


class SimilarityService:
    def __init__(self, client: Groq | None) -> None:
        self._client = client

    def compare(self, hotel: HotelProfile, competitor: HotelOffer) -> AnalysisResult:
        if self._client is None:
            return self._rule_based_result(competitor)

        prompt = f"""
Jesteś analitykiem rynku hotelarskiego w Zakopanem. Porównaj obiekty.

HOTEL WZORCOWY
Nazwa: {hotel.name}
Opis: {hotel.description}

KONKURENT
Nazwa: {competitor.name}
Cechy: {competitor.description}

Oceń podobieństwo 0–100 na podstawie standardu, SPA/Wellness, typu obiektu i lokalizacji.
Uzasadnij ocenę jednym konkretnym zdaniem po polsku. Zwróć wyłącznie JSON:
{{"score": 0, "reason": "uzasadnienie"}}
""".strip()

        try:
            response = self._client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            payload = json.loads(response.choices[0].message.content)
            score = max(0, min(100, int(payload["score"])))
            reason = str(payload["reason"]).strip()
            if not reason:
                raise ValueError("Empty analysis reason")
            return AnalysisResult(score=score, reason=reason)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Invalid Groq response for %s: %s", competitor.name, exc)
            return self._rule_based_result(competitor)
        except Exception as exc:
            logger.warning("Groq request failed for %s: %s", competitor.name, exc)
            return self._rule_based_result(competitor)

    @staticmethod
    def _rule_based_result(competitor: HotelOffer) -> AnalysisResult:
        text = f"{competitor.name} {competitor.description}".lower()
        score = 20
        signals: list[str] = []
        for keywords, points, label in (
            (("hotel",), 20, "profil hotelowy"),
            (("3*", "3-gwiazdk"), 20, "podobny standard"),
            (("spa", "wellness", "saun", "basen"), 20, "zaplecze wellness"),
            (("centrum", "krupów"), 15, "centralna lokalizacja"),
        ):
            if any(keyword in text for keyword in keywords):
                score += points
                signals.append(label)

        if "apartament" in text or "pokoje gościnne" in text:
            score -= 15
        score = max(10, min(95, score))
        detail = ", ".join(signals[:2]) or "odmienny typ i standard obiektu"
        return AnalysisResult(
            score=score,
            reason=f"{competitor.name} — kluczowe porównanie: {detail}.",
        )
