# Logos Market Pulse

Lekki panel Streamlit do porównywania ceny Hotelu Logos Zakopane z lokalnym rynkiem. Aplikacja pobiera oferty przez Apify, ocenia podobieństwo obiektów przez Groq i działa również w czytelnie oznaczonym trybie demonstracyjnym.

## Uruchomienie

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Testy regresji można uruchomić bez dodatkowego frameworka:

```powershell
python -m unittest discover -s tests
```

Kontrola jakości przed wysłaniem zmian:

```powershell
pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
```

Workflow GitHub Actions uruchamia te same kontrole automatycznie dla każdego pusha,
pull requestu oraz na żądanie z zakładki Actions.

Opcjonalne zmienne środowiskowe (lub sekrety Streamlit):

- `APIFY_API_KEY` — aktualne ceny Booking.com,
- `GROQ_API_KEY` — analiza podobieństwa generowana przez model.

Bez kluczy aplikacja korzysta z danych demonstracyjnych i lokalnej oceny podobieństwa.

## Struktura

- `app.py` — widok i orkiestracja,
- `hotel_monitor/` — modele domenowe, konfiguracja i integracje,
- `assets/theme.css` — warstwa wizualna.
