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
    "Aplikacja pobiera dane z Zakopanego z Booking.com i ocenia poziom podobieństwa obiektów za pomocą modelu Llama 3."
)

# Dane wzorcowe dla Hotelu Logos Zakopane
LOGOS_DATA = {
    "name": "Hotel Logos Zakopane",
    "description": "Hotel 3-gwiazdkowy w centrum Zakopanego. Oferuje strefę SPA (sauna, jacuzzi), restaurację Staropolska, komfortowe pokoje z widokiem na góry oraz bliskość Krupówek.",
    "capacity": 2,
}

# Sidebar - Panel wyboru dat i stawki
st.sidebar.header("📅 Wybór Terminu")
today = datetime.date.today()
check_in = st.sidebar.date_input("Data przyjazdu", today + datetime.timedelta(days=7))
check_out = st.sidebar.date_input("Data wyjazdu", today + datetime.timedelta(days=8))
my_price = st.sidebar.number_input("Twoja cena za dobę (PLN)", value=420)


def fetch_booking_data(checkin_date, checkout_date):
    """Pobiera aktualne oferty z Zakopanego za pomocą Apify."""
    if not apify_client:
        st.error("Brak skonfigurowanego APIFY_API_KEY w Secrets!")
        return []

    run_input = {
        "search": "Zakopane",
        "checkIn": checkin_date.strftime("%Y-%m-%d"),
        "checkOut": checkout_date.strftime("%Y-%m-%d"),
        "maxItems": 20,
        "adults": 2,
        "rooms": 1,
        "currency": "PLN",
    }

    try:
        # Oficjalny i aktualny Actor Booking.com w Apify
        run = apify_client.actor("datascrapers/booking-com-scraper").call(
            run_input=run_input
        )
        dataset_items = (
            apify_client.dataset(run["defaultDatasetId"]).list_items().items
        )

        results = []
        for item in dataset_items:
            name = item.get("name") or item.get("title") or item.get("hotel_name")
            price = (
                item.get("price")
                or item.get("grossPrice", {}).get("value")
                or item.get("price_raw")
            )
            rating = item.get("rating") or item.get("score") or 8.0

            if name and price:
                if isinstance(price, str):
                    price = (
                        price.replace("PLN", "")
                        .replace(" ", "")
                        .replace(",", ".")
                        .strip()
                    )
                    try:
                        price = float(price)
                    except ValueError:
                        continue

                results.append(
                    {
                        "name": name,
                        "price": float(price),
                        "capacity": 2,
                        "description": f"Ocena: {rating}/10. Obiekt w Zakopanem.",
                    }
                )
        return results

    except Exception as e:
        st.warning(
            f"Nie udało się połączyć z API Apify ({str(e)}). Ładuję przykładową bazę awaryjną dla Zakopanego..."
        )
        # Zastępcze dane na przypadek błędu połączenia
        return [
            {
                "name": "Hotel Czarny Potok 3*",
                "price": 410,
                "description": "Hotel 3-gwiazdkowy, basen, strefa SPA, centrum.",
            },
            {
                "name": "Willa pod Skocznią",
                "price": 250,
                "description": "Pokoje gościnne, śniadania, brak SPA.",
            },
            {
                "name": "Hotel Aquarion Family & SPA 4*",
                "price": 680,
                "description": "Hotel 4-gwiazdkowy, bezpośrednie wejście do Aquaparku.",
            },
            {
                "name": "Apartamenty Krupówki Premium",
                "price": 450,
                "description": "Luksusowy apartament w centrum, aneks kuchenny.",
            },
            {
                "name": "Hotel Gazdówka 3*",
                "price": 390,
                "description": "Regionalny hotel 3-gwiazdkowy z restauracją.",
            },
        ]


def analyze_similarity(my_obj, competitor_obj):
    """Sztuczna inteligencja Llama 3 analizuje poziom podobieństwa obiektów."""
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
    
    Oceń podobieństwo obiektu konkurencji do Hotelu Logos w skali od 1 do 100 
    (gdzie 100 to obiekt o identycznym standardzie 3*, strefie SPA, lokalizacji blisko centrum).
    
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


# Główny przycisk wykonawczy
if st.button("🔎 Pobierz ceny i przeanalizuj konkurencję"):
    if check_in >= check_out:
        st.error("Data wyjazdu musi być późniejsza niż data przyjazdu!")
    else:
        with st.spinner("1/2: Pobieranie aktualnych cen z Zakopanego..."):
            competitors = fetch_booking_data(check_in, check_out)

        if competitors:
            st.success(f"Analizuję {len(competitors)} pozyskanych ofert...")

            with st.spinner(
                "2/2: Sztuczna inteligencja porównuje oferty z Hotele Logos..."
            ):
                results = []
                progress_bar = st.progress(0)

                for idx, comp in enumerate(competitors):
                    ai_res = analyze_similarity(LOGOS_DATA, comp)
                    results.append(
                        {
                            "Obiekt w Zakopanem": comp.get("name"),
                            "Cena za dobę (PLN)": comp.get("price"),
                            "Podobieństwo do Logos (%)": ai_res.get("score"),
                            "Uzasadnienie oceny AI": ai_res.get("reason"),
                        }
                    )
                    progress_bar.progress((idx + 1) / len(competitors))

            df = pd.DataFrame(results)

            st.subheader("📊 Podsumowanie Analizy Cenowej")

            # Filtrujemy do podsumowania obiekty o podobieństwie przynajmniej 50%
            similar_df = df[df["Podobieństwo do Logos (%)"] >= 50]

            col1, col2, col3 = st.columns(3)
            col1.metric("Twoja uśredniona cena", f"{my_price} PLN")

            if not similar_df.empty:
                avg_price = round(similar_df["Cena za dobę (PLN)"].mean(), 2)
                col2.metric(
                    "Średnia cena podobnych obiektów", f"{avg_price} PLN"
                )
                diff = round(my_price - avg_price, 2)
                col3.metric(
                    "Różnica względem rynku", f"{diff} PLN", delta_color="inverse"
                )
            else:
                col2.metric("Średnia cena podobnych", "Brak ścisłych dopasowań")

            st.dataframe(
                df.sort_values(by="Podobieństwo do Logos (%)", ascending=False),
                use_container_width=True,
            )
