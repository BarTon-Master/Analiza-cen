import datetime
import json
import os
import pandas as pd
import streamlit as st
from apify_client import ApifyClient
from groq import Groq

# Inicjalizacja klientów API z bezpiecznych sekretów
groq_api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
apify_api_key = st.secrets.get("APIFY_API_KEY") or os.getenv("APIFY_API_KEY")

groq_client = Groq(api_key=groq_api_key)
apify_client = ApifyClient(apify_api_key)

st.set_page_config(page_title="Hotel Logos - Monitor Cen", layout="wide")

st.title("🏨 Automatyczny Porównywarka Cen dla Hotelu Logos Zakopane")
st.write(
    "Aplikacja automatycznie pobiera aktualne ceny z Zakopanego z Booking.com i porównuje je za pomocą AI."
)

# Sztywne dane Hotelu Logos
LOGOS_DATA = {
    "name": "Hotel Logos Zakopane",
    "description": "Hotel 3-gwiazdkowy w centrum Zakopanego. Oferuje pokoje z Wi-Fi, strefę SPA (sauny, jacuzzi), restaurację Staropolska oraz widok na góry. Wysoki standard, blisko Krupówek.",
    "capacity": 2,
}

# Sidebar - Ustawienia Wyszukiwania
st.sidebar.header("📅 Wybierz Termin")
today = datetime.date.today()
check_in = st.sidebar.date_input("Data przyjazdu", today + datetime.timedelta(days=7))
check_out = st.sidebar.date_input(
    "Data wyjazdu", today + datetime.timedelta(days=8)
)
my_price = st.sidebar.number_input(
    "Twoja cena za dobę dla 2 osób (PLN)", value=420
)


def fetch_booking_data(checkin_date, checkout_date):
    """Pobiera 20 ofert z Zakopanego z Booking.com przez Apify."""
    run_input = {
        "search": "Zakopane",
        "checkIn": checkin_date.strftime("%Y-%m-%d"),
        "checkOut": checkout_date.strftime("%Y-%m-%d"),
        "maxItems": 20,
        "adults": 2,
        "rooms": 1,
        "currency": "PLN",
    }
    # Użycie oficjalnego i sprawdzonego scrapera Booking.com
    run = apify_client.actor("apify/booking-scraper").call(run_input=run_input)
    dataset_items = apify_client.dataset(
        run["defaultDatasetId"]
    ).list_items().items

    results = []
    for item in dataset_items:
        # Pobież najważniejsze dane
        name = item.get("name") or item.get("title")
        price = item.get("price") or item.get("grossPrice", {}).get("value")
        rating = item.get("rating") or item.get("score")
        room_type = item.get("roomType", "Pokój 2-osobowy")

        if name and price:
            # Czyszczenie ceny, jeśli jest tekstem
            if isinstance(price, str):
                price = float(
                    price.replace("PLN", "").replace(" ", "").replace(",", ".")
                )

            results.append(
                {
                    "name": name,
                    "price": float(price),
                    "capacity": 2,
                    "description": f"Ocena: {rating}/10. Typ: {room_type}. Obiekt w Zakopanem.",
                }
            )
    return results


def analyze_similarity(my_obj, competitor_obj):
    """Sztuczna inteligencja Llama 3 ocenia podobieństwo do Hotelu Logos."""
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
    except Exception as e:
        return {"score": 50, "reason": "Średni standard (domyślny)"}


# Przycisk uruchamiający
if st.button("🔎 Pobierz aktualne ceny i przeanalizuj konkurencję"):
    if check_in >= check_out:
        st.error("Data wyjazdu musi być późniejsza niż data przyjazdu!")
    else:
        with st.spinner("1/2: Pobieram 20 obiektów z Booking.com dla Zakopanego... (może to zająć ok. 30-60 sekund)"):
            competitors = fetch_booking_data(check_in, check_out)

        if not competitors:
            st.warning("Nie udało się pobrać danych z Booking. Wypróbuj inne daty.")
        else:
            st.success(f"Pobrano {len(competitors)} aktualnych ofert!")

            with st.spinner("2/2: Sztuczna inteligencja ocenia podobieństwo obiektów do Hotelu Logos..."):
                results = []
                progress_bar = st.progress(0)

                for idx, comp in enumerate(competitors):
                    ai_res = analyze_similarity(LOGOS_DATA, comp)
                    results.append(
                        {
                            "Obiekt w Zakopanem": comp.get("name"),
                            "Cena za termin (PLN)": comp.get("price"),
                            "Podobieństwo do Logos (%)": ai_res.get("score"),
                            "Dlaczego taka ocena?": ai_res.get("reason"),
                        }
                    )
                    progress_bar.progress((idx + 1) / len(competitors))

            df = pd.DataFrame(results)

            st.subheader("📊 Wyniki i Raport Cenowy")

            # Obliczanie średnich dla obiektów najbardziej podobnych (od 60% podobieństwa)
            similar_df = df[df["Podobieństwo do Logos (%)"] >= 60]

            col1, col2, col3 = st.columns(3)
            col1.metric("Twoja cena w Logos", f"{my_price} PLN")

            if not similar_df.empty:
                avg_price = round(similar_df["Cena za termin (PLN)"].mean(), 2)
                col2.metric("Średnia cena podobnych 3* w Zakopanem", f"{avg_price} PLN")
                diff = round(my_price - avg_price, 2)
                col3.metric("Różnica vs konkurencja", f"{diff} PLN", delta_color="inverse")
            else:
                col2.metric("Średnia cena podobnych", "Brak ścisłych dopasowań")

            st.dataframe(
                df.sort_values(by="Podobieństwo do Logos (%)", ascending=False),
                use_container_width=True,
            )
