from __future__ import annotations

from hotel_monitor.models import HotelProfile

LOGOS_PROFILE = HotelProfile(
    name="Hotel Logos Zakopane",
    description=(
        "Hotel 3-gwiazdkowy w centrum Zakopanego przy ul. Grunwaldzkiej. "
        "Oferuje strefę SPA z saunami i jacuzzi, restaurację Staropolską, "
        "sale konferencyjne, widok na Tatry i wysoki standard obsługi."
    ),
    url="https://www.booking.com/hotel/pl/logos-zakopane.pl.html",
)

APIFY_ACTORS = (
    "voyager/booking-scraper",
    "dtrungtin/simple-booking-scraper",
    "webdatalabs/booking-scraper-pro",
)

APP_COPY = {
    "footer": "Narzędzie wspiera decyzje cenowe — nie zastępuje systemu revenue management.",
}
