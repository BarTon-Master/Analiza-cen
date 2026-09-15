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
    "Aplikacja pobiera 50 ofert z Zakopanego z Booking.com, wykrywa cenę Hotelu Logos oraz ocenia podobieństwo obiektów konkurencji."
)

# Dane wzorcowe dla Hotelu Logos Zakopane
LOGOS_DATA = {
    "name": "Hotel Logos Zakopane",
    "description": "Hotel 3-gwiazdkowy w centrum Zakopanego. Oferuje strefę SPA (sauna, jacuzzi), restaurację Staropolska, komfortowe pokoje z widokiem na góry oraz bliskość Krupówek.",
    "capacity": 2,
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


def fetch_booking_data(checkin_date, checkout_date):
    """Pobiera do 50 ofert z Zakopanego za pomocą Apify z automatycznym doborem dostępnego Actora."""
    if not apify_client:
        st.error("Brak skonfigurowanego APIFY_API_KEY w Secrets!")
        return []

    run_input = {
        "search": "Zakopane",
        "searchLocation": "Zakopane",
        "checkIn": checkin_date.strftime("%Y-%m-%d"),
        "checkOut": checkout_date.strftime("%Y-%m-%d"),
        "maxItems": 50,
        "adults": 2,
        "rooms": 1,
        "currency": "PLN",
    }

    # Lista nazw sprawnych Actorów na Apify
    actor_candidates = [
        "voyager/booking-scraper",
        "dtrungtin/simple-booking-scraper",
        "webdatalabs/booking-scraper-pro",
    ]

    run = None
    last_error = ""

    for actor_id in actor_candidates:
        try:
            st.info(f"Łączenie z Apify Actor: `{actor_id}`...")
            run = apify_client.actor(actor_id).call(run_input=run_input)
            if run:
                break
        except Exception as e:
            last_error = str(e)
            continue

    if not run:
        st.warning(
            f"Nie udało się połączyć z API Apify ({last_error}). Ładuję przykładową bazę awaryjną..."
        )
        return get_fallback_data(num_nights)

    try:
        # Pobranie dataset_id
        if isinstance(run, dict):
            dataset_id = run.get("defaultDatasetId")
        else:
            dataset_id = getattr(
                run, "default_dataset_id", getattr(run, "defaultDatasetId", None)
            )

        if not dataset_id and hasattr(run, "__getitem__"):
            dataset_id = run["defaultDatasetId"]

        dataset_items = apify_client.dataset(dataset_id).list_items().items

        results = []
        for item in dataset_items:
            name = item.get("name") or item.get("title") or item.get("hotel_name")
            raw_price = (
                item.get("price")
                or item.get("grossPrice", {}).get("value")
                or item.get("price_raw")
            )
            rating = item.get("rating") or item.get("score") or 8.0

            if name and raw_price:
                if isinstance(raw_price, str):
                    raw_price = (
                        raw_price.replace("PLN", "")
                        .replace(" ", "")
                        .replace(",", ".")
                        .strip()
                    )
                    try:
                        raw_price = float(raw_price)
                    except ValueError:
                        continue

                # Niektóre scrapery zwracają cenę za całe zamówienie, inne za dobę.
                # Standardowo w Apify zwracana jest cena łączna za pobyt.
                total_price = float(raw_price)
                daily_price = (
                    round(total_price / num_nights, 2)
                    if num_nights > 0
                    else total_price
                )

                results.append(
                    {
                        "name": name,
                        "daily_price": daily_price,
                        "total_price": total_price,
                        "description": f"Ocena: {rating}/10. Obiekt w Zakopanem.",
                    }
                )
        return results if results else get_fallback_data(num_nights)

    except Exception as e:
        st.warning(
            f"Błąd przetwarzania danych z Apify: {str(e)}. Ładuję przykładową bazę..."
        )
        return get_fallback_data(num_nights)


def get_fallback_data(nights):
    """Baza zastępcza z rozszerzoną listą obiektów."""
    items = [
        ("Hotel Logos Zakopane", 420),
        ("Hotel Czarny Potok 3*", 410),
        ("Willa pod Skocznią", 250),
        ("Hotel Aquarion Family & SPA 4*", 680),
        ("Apartamenty Krupówki Premium", 450),
        ("Hotel Gazdówka 3*", 390),
        ("Grand Hotel Stamford Zakopane 5*", 920),
        ("Hotel Belvedere Resort & SPA", 580),
        ("Resort Nosalowy Dwór 4*", 610),
        ("Aparthotel Giewont", 490),
        ("Hotel Mercure Kasprowy", 530),
        ("Hotel Radisson Blu Resort", 750),
        ("Willa Carlton", 280),
        ("Hotel Sabala 3*", 430),
        ("Willa ORLA", 290),
    ]

    results = []
    for name, daily in items:
        results.append(
            {
                "name": name,
                "daily_price": daily,
                "total_price": daily * nights,
                "description": f"Obiekt w Zakopanem.",
            }
        )
    return results


def analyze_similarity(my_obj, competitor_obj):
    """Analiza podobieństwa obiektów przez model Llama 3."""
    if not groq_client:
        return {"score": 50, "reason": "Brak klucza Groq API"}

    prompt = f"""
    Jesteś ekspertem rynku hotelarskiego w Zakopanem. 
    Porównaj nasz obiekt wzorcowy (Hotel Logos Zakopane) z obiektem konkurencji.
    
    NASZ HOTEL:
    - Nazwa: {my_obj['name']}
    - Standard i Opis: {my_obj['description']}
    
    OBIEKT KONKURENCJI Z BOOKING.COM:
    - Nazwa: {competitor_obj.get('name')}
    - Opis/Informacje: {competitor_obj.get('description')}
    
    Oceń podobieństwo obiektu konkurencji do Hotelu Logos w skali od 1 do 100.
    
    Odpowiedz WYŁĄCZNIE czystym formatem JSON bez żadnych dopisków:
    {{"score": liczba_całkowita_1_100, "reason": "krótkie uzasadnienie po polsku w 1 zdaniu"}}
    """

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()
        if "{" in content:
            content = content[content.find("{") : content.rfind("}") + 1]
        return json.loads(content)
    except Exception:
        return {
            "score": 50,
            "reason": "Standardowy obiekt noclegowy w Zakopanem.",
        }


# Przycisk uruchamiający
if st.button("🔎 Pobierz 50 obiektów i przeanalizuj rynek"):
    if num_nights <= 0:
        st.error("Wybierz poprawny zakres dat!")
    else:
        with st.spinner(
            f"1/2: Pobieranie do 50 aktualnych cen z Zakopanego z Booking.com dla pobytu na {num_nights} nocy... (trwa ok. 30-60 sekund)"
        ):
            competitors = fetch_booking_data(check_in, check_out)

        if competitors:
            # Automatyczne szukanie ceny Hotelu Logos w pobranych wynikach
            logos_found = next(
                (c for c in competitors if "logos" in c["name"].lower()), None
            )

            if logos_found:
                logos_daily_price = logos_found["daily_price"]
                logos_total_price = logos_found["total_price"]
                st.success(
                    f"Wyryto cenę Hotelu Logos dla wybranego terminu: **{logos_daily_price} PLN/doba** (Łącznie: {logos_total_price} PLN za {num_nights} nocy)."
                )
            else:
                logos_daily_price = 420.0
                logos_total_price = logos_daily_price * num_nights
                st.info(
                    f"Nie znaleziono Hotelu Logos w pierwszych wynikach Booking. Uszyto cenę bazową: **{logos_daily_price} PLN/doba**."
                )

            st.write(f"Rozpoczynam analizę AI dla {len(competitors)} ofert...")

            with st.spinner(
                "2/2: AI porównuje oferty pod kątem standardu i lokalizacji z Hotele Logos..."
            ):
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
                            "Uzasadnienie AI": ai_res.get("reason"),
                        }
                    )
                    progress_bar.progress((idx + 1) / len(competitors))

            df = pd.DataFrame(results)

            st.subheader("📊 Podsumowanie Analizy Cenowej Rywalizacji")

            # Filtrowanie obiektów o podobieństwie przynajmniej 50%
            similar_df = df[df["Podobieństwo do Logos (%)"] >= 50]

            col1, col2, col3 = st.columns(3)
            col1.metric("Cena Logos (doba)", f"{logos_daily_price} PLN")

            if not similar_df.empty:
                avg_daily = round(similar_df["Cena / Dzień (PLN)"].mean(), 2)
                col2.metric(
                    "Średnia cena podobnych (doba)", f"{avg_daily} PLN"
                )
                diff = round(logos_daily_price - avg_daily, 2)
                col3.metric(
                    "Różnica dzienna", f"{diff} PLN", delta_color="inverse"
                )
            else:
                col2.metric("Średnia cena podobnych", "Brak dopasowań")

            # Wyświetlenie pełnej tabeli z sortowaniem po podobieństwie
            st.dataframe(
                df.sort_values(by="Podobieństwo do Logos (%)", ascending=False),
                use_container_width=True,
            )
