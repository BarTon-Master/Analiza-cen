import json
import os
import pandas as pd
import streamlit as st
from openai import OpenAI

# Inicjalizacja klienta OpenAI z klucza w bezpiecznych ustawieniach Streamlit
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

st.set_page_config(page_title="Monitor Cen Noclegów AI", layout="wide")

st.title("🏨 Analizator i Porównywarka Cen Noclegów AI")
st.write(
    "Aplikacja porównuje Twój obiekt z konkurencją i szacuje wynik podobieństwa za pomocą AI."
)

# Sidebar - Dane Twojego Obiektu
st.sidebar.header("🎯 Twój Obiekt")
my_name = st.sidebar.text_input("Nazwa obiektu", "Apartament Słoneczny Park")
my_price = st.sidebar.number_input("Twoja obecna cena (PLN)", value=350)
my_capacity = st.sidebar.number_input("Maks. liczba osób", value=4)
my_description = st.sidebar.text_area(
    "Opis / Udogodnienia",
    "Apartament 45m2, 2 pokoje, balkon, szybkie Wi-Fi, sauna, 500m od centrum.",
)


def analyze_similarity(my_obj, competitor_obj):
    prompt = f"""
    Jesteś ekspertem ds. wyceny nieruchomości i noclegów. 
    Porównaj poniższy obiekt wzorcowy z obiektem konkurencji.
    
    OBIEKT WZORCOWY:
    - Pojemność: {my_obj['capacity']} osób
    - Opis: {my_obj['description']}
    
    OBIEKT KONKURENCJI:
    - Nazwa: {competitor_obj.get('name')}
    - Pojemność: {competitor_obj.get('capacity')} osób
    - Opis: {competitor_obj.get('description')}
    
    Oceń podobieństwo obiektu konkurencji do obiektu wzorcowego w skali od 1 do 100 
    (gdzie 100 to niemal identyczny standard, wielkość, lokalizacja i udogodnienia).
    
    Odpowiedz TYLKO w formacie JSON:
    {{"score": liczba_całkowita_1_100, "reason": "krotkie_uzasadnienie_w_1_zdaniu"}}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"score": 0, "reason": f"Błąd API: {str(e)}"}


# Wczytywanie danych konkurencji
st.subheader("1. Wczytaj dane konkurencji (JSON)")
uploaded_file = st.file_uploader("Wgraj plik JSON z ofertami", type=["json"])

default_data = [
    {
        "name": "Apartament Górski Widok",
        "price": 380,
        "capacity": 4,
        "description": "40m2, balkon, widok na góry, dostęp do strefy SPA i sauny.",
    },
    {
        "name": "Pokoje Gościnne U Basi",
        "price": 180,
        "capacity": 2,
        "description": "Mały pokój dwuosobowy, wspólna łazienka, skromne wyposażenie.",
    },
    {
        "name": "Luksusowy Penthouse Centrum",
        "price": 750,
        "capacity": 6,
        "description": "100m2, prywatne jacuzzi, taras, standard 5-gwiazdkowy.",
    },
    {
        "name": "Słoneczne Mieszkanie przy Parku",
        "price": 340,
        "capacity": 4,
        "description": "42m2, 2 pokoje, blisko parku, zmywarka, szybki internet.",
    },
]

if uploaded_file is not None:
    competitors = json.load(uploaded_file)
else:
    st.info(
        "Używam przykładowych danych testowych. Możesz wgrać własny plik JSON powyżej."
    )
    competitors = default_data

if st.button("🚀 Uruchom analizę podobieństwa przez AI"):
    my_object_data = {"capacity": my_capacity, "description": my_description}

    results = []
    progress_bar = st.progress(0)

    for idx, comp in enumerate(competitors):
        ai_res = analyze_similarity(my_object_data, comp)
        results.append(
            {
                "Nazwa obiektu": comp.get("name"),
                "Cena (PLN)": comp.get("price"),
                "Liczba osób": comp.get("capacity"),
                "Podobieństwo AI (%)": ai_res.get("score"),
                "Uzasadnienie AI": ai_res.get("reason"),
            }
        )
        progress_bar.progress((idx + 1) / len(competitors))

    df = pd.DataFrame(results)

    st.subheader("2. Wyniki Analizy")

    similar_df = df[df["Podobieństwo AI (%)"] >= 50]

    col1, col2, col3 = st.columns(3)
    col1.metric("Twoja cena", f"{my_price} PLN")

    if not similar_df.empty:
        avg_similar_price = round(similar_df["Cena (PLN)"].mean(), 2)
        col2.metric("Średnia cena podobnych (AI ≥ 50%)", f"{avg_similar_price} PLN")

        diff = round(my_price - avg_similar_price, 2)
        col3.metric("Różnica", f"{diff} PLN", delta_color="inverse")
    else:
        col2.metric("Średnia cena podobnych", "Brak dopasowań")

    st.dataframe(
        df.sort_values(by="Podobieństwo AI (%)", ascending=False),
        use_container_width=True,
    )
