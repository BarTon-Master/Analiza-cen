from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from apify_client import ApifyClient
from groq import Groq

from hotel_monitor.config import APP_COPY, LOGOS_PROFILE
from hotel_monitor.models import AnalysisResult, HotelOffer
from hotel_monitor.services import MarketService, SimilarityService

st.set_page_config(
    page_title="Logos Market Pulse",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _load_theme() -> None:
    css_path = Path(__file__).parent / "assets" / "theme.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:  # No secrets file in local/demo environments.
        value = None
    return value or os.getenv(name)


@st.cache_resource(show_spinner=False)
def _build_services(
    apify_api_key: str | None, groq_api_key: str | None
) -> tuple[MarketService, SimilarityService]:
    apify = ApifyClient(apify_api_key) if apify_api_key else None
    groq = Groq(api_key=groq_api_key) if groq_api_key else None
    return MarketService(apify), SimilarityService(groq)


def _format_pln(value: float) -> str:
    return f"{value:,.0f} zł".replace(",", " ")


def _render_header() -> None:
    st.markdown(
        """
        <nav class="top-nav">
            <div class="brand"><span class="brand-mark">L</span><span>Logos Market Pulse<small>REVENUE INTELLIGENCE</small></span></div>
            <div class="system-status"><i></i>SYSTEM GOTOWY</div>
        </nav>
        <section class="hero-shell">
            <div class="hero-glow"></div>
            <div class="hero-content">
                <span class="hero-badge">ZAKOPANE · COMPETITIVE SET</span>
                <h1>Cena, która<br><em>pracuje mądrzej.</em></h1>
                <p>Zobacz pozycję Hotelu Logos na tle rynku. Szybki benchmark, trafne porównania i jedna czytelna rekomendacja.</p>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_search() -> tuple[dt.date, dt.date, int, int, int, bool]:
    today = dt.date.today()
    with st.form("search_form", border=False):
        check_in_column, check_out_column, action_column = st.columns([1, 1, 0.72])
        with check_in_column:
            check_in = st.date_input(
                "Przyjazd",
                today + dt.timedelta(days=7),
                min_value=today,
                format="DD.MM.YYYY",
            )
        with check_out_column:
            check_out = st.date_input(
                "Wyjazd",
                today + dt.timedelta(days=8),
                min_value=today + dt.timedelta(days=1),
                format="DD.MM.YYYY",
            )
        with action_column:
            submitted = st.form_submit_button(
                "Analizuj rynek  →", type="primary", use_container_width=True
            )

        with st.expander("Więcej opcji"):
            guests_column, rooms_column, results_column = st.columns(3)
            adults = guests_column.selectbox("Goście", (1, 2, 3, 4), index=1)
            rooms = rooms_column.selectbox("Pokoje", (1, 2, 3), index=0)
            max_items = results_column.selectbox("Liczba porównań", (10, 15, 20), index=2)

        nights = max((check_out - check_in).days, 0)
        night_label = "noc" if nights == 1 else "noce" if 2 <= nights <= 4 else "nocy"
        st.markdown(
            f'<div class="search-summary"><span>✓</span>{adults} gości · {rooms} pokój/pokoje · {nights} {night_label} · do {max_items} ofert</div>',
            unsafe_allow_html=True,
        )
    return check_in, check_out, adults, rooms, max_items, submitted


def _render_error_state(message: str) -> None:
    st.markdown(
        f"""
        <div class="error-state">
            <span>!</span>
            <div><strong>Nie udało się przygotować analizy</strong><p>{message}</p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _run_analysis(
    market_service: MarketService,
    similarity_service: SimilarityService,
    check_in: dt.date,
    check_out: dt.date,
    adults: int,
    rooms: int,
    max_items: int,
) -> None:
    if check_out <= check_in:
        _render_error_state("Data wyjazdu musi być późniejsza niż data przyjazdu.")
        return

    try:
        with st.spinner("Pobieram aktualne ceny rynkowe…"):
            snapshot = market_service.get_snapshot(
                check_in,
                check_out,
                adults=adults,
                rooms=rooms,
                max_items=max_items,
            )

        competitors = [offer for offer in snapshot.offers if "logos" not in offer.name.lower()]
        if not competitors:
            _render_error_state("Brak ofert dla wybranych parametrów. Zmień termin lub opcje.")
            return

        analyses: list[AnalysisResult] = []
        progress = st.progress(0, text="Oceniam podobieństwo obiektów…")
        for index, competitor in enumerate(competitors):
            analyses.append(similarity_service.compare(LOGOS_PROFILE, competitor))
            progress.progress(
                (index + 1) / len(competitors),
                text=f"Analizuję rynek · {index + 1}/{len(competitors)}",
            )
        progress.empty()
    except Exception:
        _render_error_state(
            "Spróbuj ponownie za chwilę. Jeśli problem wraca, sprawdź konfigurację API."
        )
        return

    st.session_state["report"] = {
        "snapshot": snapshot,
        "competitors": competitors,
        "analyses": analyses,
        "check_in": check_in,
        "check_out": check_out,
    }


def _report_dataframe(
    competitors: list[HotelOffer], analyses: list[AnalysisResult]
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Obiekt": offer.name,
                "Cena / noc": offer.nightly_price,
                "Cena pobytu": offer.total_price,
                "Podobieństwo": analysis.score,
                "Komentarz": analysis.reason,
            }
            for offer, analysis in zip(competitors, analyses, strict=True)
        ]
    ).sort_values(["Podobieństwo", "Cena / noc"], ascending=[False, True])


def _render_empty_state() -> None:
    st.markdown(
        """
        <section class="empty-section">
            <div class="section-heading"><span>CO OTRZYMASZ</span><h2>Decyzja cenowa bez zgadywania.</h2></div>
            <div class="feature-grid">
                <article><b>01</b><h3>Aktualny benchmark</h3><p>Cena Logos zestawiona z porównywalnymi ofertami w Zakopanem.</p></article>
                <article><b>02</b><h3>Trafny competitive set</h3><p>Podobieństwo według standardu, SPA, typu obiektu i lokalizacji.</p></article>
                <article><b>03</b><h3>Czytelna pozycja</h3><p>Od razu widzisz, czy oferta jest powyżej czy poniżej rynku.</p></article>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_report() -> None:
    report = st.session_state.get("report")
    if not report:
        _render_empty_state()
        return

    snapshot = report["snapshot"]
    competitors = report["competitors"]
    analyses = report["analyses"]
    check_in = report["check_in"]
    check_out = report["check_out"]
    frame = _report_dataframe(competitors, analyses)

    similar = frame[frame["Podobieństwo"] >= 50]
    benchmark = similar if not similar.empty else frame
    average_price = float(benchmark["Cena / noc"].mean())
    price_delta = snapshot.logos_nightly_price - average_price
    market_position = "powyżej" if price_delta > 0 else "poniżej"
    source_label = "DANE LIVE" if snapshot.is_live else "TRYB DEMO"
    source_class = "live" if snapshot.is_live else "demo"

    st.markdown(
        f"""
        <div class="report-heading">
            <div><span>RAPORT RYNKOWY</span><h2>{check_in:%d.%m} — {check_out:%d.%m.%Y}</h2></div>
            <b class="source-pill {source_class}">{source_label}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("LOGOS · CENA / NOC", _format_pln(snapshot.logos_nightly_price))
    metric_2.metric("RYNEK · ŚREDNIA", _format_pln(average_price))
    metric_3.metric(
        "RÓŻNICA DO RYNKU",
        _format_pln(abs(price_delta)),
        delta=f"{market_position} benchmarku",
        delta_color="inverse" if price_delta > 0 else "normal",
    )
    metric_4.metric("PORÓWNANE OBIEKTY", str(len(frame)))

    if snapshot.warnings:
        st.caption(" · ".join(snapshot.warnings))

    st.markdown("### Najbliższa konkurencja")
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Obiekt": st.column_config.TextColumn("OBIEKT", width="medium"),
            "Cena / noc": st.column_config.NumberColumn("CENA / NOC", format="%d zł"),
            "Cena pobytu": st.column_config.NumberColumn("POBYT", format="%d zł"),
            "Podobieństwo": st.column_config.ProgressColumn(
                "DOPASOWANIE", min_value=0, max_value=100, format="%d%%"
            ),
            "Komentarz": st.column_config.TextColumn("KOMENTARZ", width="large"),
        },
        height=min(680, 74 + len(frame) * 46),
    )


_load_theme()
market_service, similarity_service = _build_services(
    _secret("APIFY_API_KEY"), _secret("GROQ_API_KEY")
)
_render_header()
check_in, check_out, adults, rooms, max_items, submitted = _render_search()

if submitted:
    _run_analysis(
        market_service,
        similarity_service,
        check_in,
        check_out,
        adults,
        rooms,
        max_items,
    )

_render_report()

st.markdown(
    f'<footer><span>{APP_COPY["footer"]}</span><a href="{LOGOS_PROFILE.url}" target="_blank">Hotel Logos Zakopane ↗</a></footer>',
    unsafe_allow_html=True,
)
