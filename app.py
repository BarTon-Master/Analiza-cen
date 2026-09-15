import datetime
import json
import os
import pandas as pd
import streamlit as st
from apify_client import ApifyClient
from groq import Groq

# 1. Inicjalizacja kluczy API z Secrets w Streamlit Cloud
groq_api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
apify_api_key = st.secrets.get("APIFY_API_KEY") or os.getenv("APIFY_API_KEY")

groq_client = Groq(api_key=groq_api_key) if groq_api_key else None
apify_client = ApifyClient(apify_api_key) if apify_api_key else None

st.set_page_config(page_title="Hotel Logos - Monitor Cen AI", layout="wide")

st.title("🏨 Porównywarka Cen AI dla Hotelu Logos Zakopane")
st.write(
    "Aplikacja pobiera ofertę bezpośrednio z profilu **Hotel Logos Zakopane** na Booking.com, porównuje ją z 20 obiektami konkurencji i generuje unikalną analizę podobieństwa za pomocą Llama 3."
)

# Dane wzorcowe dla Hotelu Logos Zakopane z oficjalnego linku
LOGOS_URL = "https://www.booking.com/hotel/pl/logos-zakopane.pl.html"
LOGOS_DATA = {
    "name": "Hotel Logos Zakopane",
    "description": "Hotel 3-gwiazdkowy w centrum Zakopanego (ul. Grunwaldzka). Strefa SPA (sauny, jacuzzi, studio modelowania sylwetki), restauracja Staropolska, sale konferencyjne, widok na Tatry, wysoki standard obsługi.",
    "url": LOGOS_URL,
}

# Sidebar - Panel wyboru dat
st.sidebar.header("📅 Wybór Terminu")
today = datetime.date.today()
check_in = st.sidebar.date_input("Data przyjazdu", today + datetime.timedelta(days=7))
check_out = st.sidebar.date_input("Data wyjazdu", today + datetime.timedelta(days=8))

# Obliczenie liczby nocy
num_nights = (check_out - check_in).days
if num_nights <= 0:
    st.sidebar.error("Data wyjazdu musi być późniejsza niż przyjazdu!")
else:
    st.sidebar.info(f"Długość pobytu: **{num_nights} nocy/noc**")


def fetch_logos_exact_price(checkin_date, checkout_date):
    """Pobiera cenę bezpośrednio z podanego URL Hotelu Logos."""
    if not apify_client:
        return None

    run_input = {
        "startUrls": [{"url": LOGOS_URL}],
        "checkIn": checkin_date.strftime("%Y-%m-%d"),
        "checkOut": checkout_date.strftime("%Y-%m-%d"),
        "adults": 2,
        "rooms": 1,
        "currency": "PLN",
    }

    actor_candidates = ["voyager/booking-scraper", "dtrungtin/simple-booking-scraper"]

    for actor_id in actor_candidates:
        try:
            run = apify_client.actor(actor_id).call(run_input=run_input)
            dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else getattr(run, "default_dataset_id", None)
            items = apify_client.dataset(dataset_id).list_items().items
            if items:
                raw_price = items[0].get("price") or items[0].get("grossPrice", {}).get("value")
                if raw_price:
                    if isinstance(raw_price, str):
                        raw_price = float(raw_price.replace("PLN", "").replace(" ", "").replace(",", ".").strip())
                    return float(raw_price)
        except Exception:
            continue
    return None


def fetch_booking_data(checkin_date, checkout_date):
    """Pobiera 20 ofert z Zakopanego z Booking.com."""
    if not apify_client:
        st.error("Brak skonfigurowanego APIFY_API_KEY w Secrets!")
        return []

    run_input = {
        "search": "Zakopane",
        "searchLocation": "Zakopane",
        "checkIn": checkin_date.strftime("%Y-%m-%d"),
        "checkOut": checkout_date.strftime("%Y-%m-%d"),
        "maxItems": 20,
        "adults": 2,
        "rooms": 1,
        "currency": "PLN",
    }

    actor_candidates = [
        "voyager/booking-scraper",
        "dtrungtin/simple-booking-scraper",
        "webdatalabs/booking-scraper-pro",
    ]

    run = None
    last_error = ""

    for actor_id in actor_candidates:
        try:
            run = apify_client.actor(actor_id).call(run_input=run_input)
            if run:
                break
        except Exception as e:
            last_error = str(e)
            continue

    if not run:
        st.warning(f"Nie udało się połączyć z API Apify ({last_error}). Ładuję dane zastępcze...")
        return get_fallback_data(num_nights)

    try:
        dataset_id = run.get("defaultDatasetId") if isinstance(run, dict) else getattr(run, "default_dataset_id", None)
        if not dataset_id and hasattr(run, "__getitem__"):
            dataset_id = run["defaultDatasetId"]

        dataset_items = apify_client.dataset(dataset_id).list_items().items

        results = []
        for item in dataset_items:
            name = item.get("name") or item.get("title") or item.get("hotel_name")
            raw_price = item.get("price") or item.get("grossPrice", {}).get("value") or item.get("price_raw")
            rating = item.get("rating") or item.get("score") or "Brak oceny"
            stars = item.get("stars") or item.get("ratingText") or ""
            distance = item.get("distance") or item.get("distanceFromCenter") or "nieokreślona odległość od centrum"

            if name and raw_price:
                if isinstance(raw_price, str):
                    raw_price = raw_price.replace("PLN", "").replace(" ", "").replace(",", ".").strip()
                    try:
                        raw_price = float(raw_price)
                    except ValueError:
                        continue

                total_price = float(raw_price)
                daily_price = round(total_price / num_nights, 2) if num_nights > 0 else total_price

                results.append(
                    {
                        "name": name,
                        "daily_price": daily_price,
                        "total_price": total_price,
                        "description": f"Ocena: {rating}/10, Standard/Gwiazdki: {stars}, Odległość: {distance}.",
                    }
                )
        return results if results else get_fallback_data(num_nights)

    except Exception as e:
        st.warning(f"Błąd przetwarzania danych z Apify: {str(e)}. Ładuję dane zastępcze...")
        return get_fallback_data(num_nights)


def get_fallback_data(nights):
    """Baza zastępcza na przypadek braku połączenia."""
    items = [
        ("Hotel Logos Zakopane", 420, "Hotel 3*, SPA, centrum Zakopanego"),
        ("Hotel Czarny Potok 3*", 410, "Hotel 3*, basen, strefa SPA, kameralny"),
        ("Willa pod Skocznią", 230, "Pokoje gościnne, skromne śniadania, brak strefy SPA"),
        ("Hotel Aquarion Family & SPA 4*", 670, "Luksusowy hotel 4* z bezpośrednim przejściem do Aquaparku"),
        ("Apartamenty Krupówki Premium", 460, "Prywatny apartament bez obsługi hotelowej i bez restauracji"),
        ("Hotel Gazdówka 3*", 380, "Tradycyjny hotel regionalny na obrzeżach"),
        ("Grand Hotel Stamford Zakopane 5*", 910, "Ekskluzywny pięciogwiazdkowy hotel ze strefą Wellness & SPA"),
        ("Hotel Belvedere Resort & SPA", 590, "Duży obiekt wypoczynkowo-konferencyjny ze sporym kompleksem basenowym"),
        ("Resort Nosalowy Dwór 4*", 620, "Nowoczesny resort pod Nosalem, nastawiony na narciarzy i biznes"),
        ("Aparthotel Giewont", 510, "Luksusowe apartamenty w samym sercu Krupówek ze strefą basenową"),
    ]

    results = []
    for name, daily, desc in items:
        results.append(
            {
                "name": name,
                "daily_price": daily,
                "total_price": daily * nights,
                "description": desc,
            }
        )
    return results


def analyze_similarity(my_obj, competitor_obj):
    """Sztuczna inteligencja z bardziej unikalną analizą i kontekstem."""
    if not groq_client:
        return {"score": 50, "reason": "Brak klucza Groq API"}

    prompt = f"""
    Jesteś analitykiem rynku hotelarskiego w Zakopanem. 
    Porównaj nasz hotel wzorcowy z konkretnym obiektem konkurencji i wkaż kluczowe różnice lub podobieństwa.
    
    NASZ HOTEL WZORCOWY:
    - Nazwa: {my_obj['name']}
    - Opis: {my_obj['description']}
    
    ANALIZOWANY OBIEKT KONKURENCJI:
    - Nazwa: {competitor_obj.get('name')}
    - Cechy/Szczegóły z Booking.com: {competitor_obj.get('description')}
    
    ZADANIE:
    1. Oceń poziom podobieństwa (0-100), biorąc pod uwagę: standard (gwiazdki/jakość), obecność strefy SPA/Wellness, charakter obiektu (hotel vs apartament/kwatera) oraz lokalizację.
    2. Napisz 1 zwięzłe, ale Bardzo Konkretne i Unikalne zdanie po polsku uzasadniające ocenę (odnieś się wprost do nazwy lub cech konkurenta).
    
    Odpowiedz WYŁĄCZNIE poprawnym formatem JSON:
    {{"score": liczba_całkowita, "reason": "Treść unikalnego uzasadnienia"}}
    """

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        content = response.choices[0].message.content.strip()
        if "{" in content:
            content = content[content.find("{") : content.rfind("}") + 1]
        return json.loads(content)
    except Exception:
        return {
            "score": 50,
            "reason": f"Obiekt {competitor_obj.get('name')} oferuje inny standard noclegowy.",
        }


# Przycisk uruchamiający
if st.button("🔎 Pobierz dane i przeanalizuj 20 obiektów"):
    if num_nights <= 0:
        st.error("Wybierz poprawny zakres dat!")
    else:
        with st.spinner("1/3: Sprawdzanie aktualnej ceny w profilu Hotelu Logos..."):
            exact_logos_price = fetch_logos_exact_price(check_in, check_out)

        with st.spinner(f"2/3: Pobieranie 20 ofert z Zakopanego dla pobytu na {num_nights} nocy..."):
            competitors = fetch_booking_data(check_in, check_out)

        if competitors:
            # Ustalanie ceny Hotelu Logos
            if exact_logos_price:
                logos_total_price = exact_logos_price
                logos_daily_price = round(exact_logos_price / num_nights, 2)
                st.success(f"Pobrano ze strony Hotelu Logos: **{logos_daily_price} PLN/doba** (Łącznie: {logos_total_price} PLN za {num_nights} nocy).")
            else:
                logos_found = next((c for c in competitors if "logos" in c["name"].lower()), None)
                if logos_found:
                    logos_daily_price = logos_found["daily_price"]
                    logos_total_price = logos_found["total_price"]
                    st.success(f"Wykryto Hotel Logos w wynikach: **{logos_daily_price} PLN/doba**.")
                else:
                    logos_daily_price = 420.0
                    logos_total_price = logos_daily_price * num_nights
                    st.info(f"Cena szacunkowa Hotelu Logos: **{logos_daily_price} PLN/doba**.")

            with st.spinner("3/3: Llama 3 analizuje unikalne cechy każdego obiektu..."):
                results = []
                progress_bar = st.progress(0)

                for idx, comp in enumerate(competitors):
                    ai_res = analyze_similarity(LOGOS_DATA, comp)
                    results.append(
                        {
                            "Nazwa Obiektu": comp.get("name"),
                            "Cena / Dzień (PLN)": comp.get("daily_price"),
                            "Suma Łączna (PLN)": comp.get("total_price"),
                            "Podobieństwo do Logos (%)": ai_res.get("score"),
                            "Uzasadnienie AI (Unikalne)": ai_res.get("reason"),
                        }
                    )
                    progress_bar.progress((idx + 1) / len(competitors))

            df = pd.DataFrame(results)

            st.subheader("📊 Wyniki Analizy Konkurencji")

            similar_df = df[df["Podobieństwo do Logos (%)"] >= 50]

            col1, col2, col3 = st.columns(3)
            col1.metric("Cena Logos (doba)", f"{logos_daily_price} PLN")

            if not similar_df.empty:
                avg_daily = round(similar_df["Cena / Dzień (PLN)"].mean(), 2)
                col2.metric("Średnia cena podobnych (doba)", f"{avg_daily} PLN")
                diff = round(logos_daily_price - avg_daily, 2)
                col3.metric("Różnica dzienna", f"{diff} PLN", delta_color="inverse")
            else:
                col2.metric("Średnia cena podobnych", "Brak ścisłych dopasowań")

            st.dataframe(
                df.sort_values(by="Podobieństwo do Logos (%)", ascending=False),
                use_container_width=True,
            )
