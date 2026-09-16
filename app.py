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
    initial_sidebar_state="expanded",
)


def _load_theme() -> None:
    css_path = Path(__file__).parent / "assets" / "theme.css"
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def _secret(name: str) -> str | None:
    """Read Cloud secrets safely, then fall back to the local environment."""
    try:
        value = st.secrets.get(name)
    except Exception:  # Streamlit raises a dedicated error when no secrets file exists.
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
        <div class="brand-row">
            <div class="brand-mark">L</div>
            <div class="brand-name">LOGOS <span>MARKET PULSE</span></div>
            <div class="status-pill"><i></i> REVENUE INTELLIGENCE</div>
        </div>
        <section class="hero">
            <p class="eyebrow">ZAKOPANE · COMPETITIVE SET</p>
            <h1>Właściwa cena.<br><em>Lepsza decyzja.</em></h1>
            <p class="hero-copy">Porównaj pozycję Hotelu Logos z lokalnym rynkiem i zobacz, gdzie naprawdę powstaje przewaga cenowa.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> tuple[dt.date, dt.date, bool]:
    today = dt.date.today()
    with st.sidebar:
        st.markdown('<p class="sidebar-kicker">PARAMETRY ANALIZY</p>', unsafe_allow_html=True)
        st.markdown("## Pobyt")
        with st.form("search_form", border=False):
            check_in = st.date_input(
                "Przyjazd",
                today + dt.timedelta(days=7),
                min_value=today,
                format="DD.MM.YYYY",
            )
            check_out = st.date_input(
                "Wyjazd",
                today + dt.timedelta(days=8),
                min_value=today + dt.timedelta(days=1),
                format="DD.MM.YYYY",
            )
            nights = max((check_out - check_in).days, 0)
            night_label = "noc" if nights == 1 else "noce" if 2 <= nights <= 4 else "nocy"
            st.markdown(
                f'<div class="stay-summary"><span>DŁUGOŚĆ POBYTU</span><strong>{nights} {night_label}</strong></div>',
                unsafe_allow_html=True,
            )
            submitted = st.form_submit_button(
                "Uruchom analizę  →", type="primary", use_container_width=True
            )

        st.markdown(
            """
            <div class="sidebar-note">
                <span>METODOLOGIA</span>
                <p>Ceny dla 2 osób i 1 pokoju. Podobieństwo uwzględnia standard, SPA, typ obiektu i lokalizację.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return check_in, check_out, submitted


def _run_analysis(
    market_service: MarketService,
    similarity_service: SimilarityService,
    check_in: dt.date,
    check_out: dt.date,
) -> None:
    nights = (check_out - check_in).days
    if nights <= 0:
        st.error("Data wyjazdu musi być późniejsza niż data przyjazdu.")
        return

    with st.spinner("Pobieram aktualne ceny rynkowe…"):
        snapshot = market_service.get_snapshot(check_in, check_out)

    competitors = [offer for offer in snapshot.offers if "logos" not in offer.name.lower()]
    if not competitors:
        st.error("Nie znaleziono ofert do porównania. Spróbuj ponownie później.")
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


def _render_report() -> None:
    report = st.session_state.get("report")
    if not report:
        st.markdown(
            """
            <div class="empty-state">
                <span>01</span>
                <h3>Twój rynek w jednym widoku</h3>
                <p>Wybierz termin i uruchom analizę. Otrzymasz benchmark cenowy oraz ranking najbardziej zbliżonych obiektów.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
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

    st.markdown(
        f"""
        <div class="report-heading">
            <div><p class="eyebrow">RAPORT RYNKOWY</p><h2>{check_in:%d.%m} — {check_out:%d.%m.%Y}</h2></div>
            <div class="source-pill {"live" if snapshot.is_live else "demo"}">{source_label}</div>
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
selected_check_in, selected_check_out, search_submitted = _render_sidebar()

if search_submitted:
    _run_analysis(
        market_service,
        similarity_service,
        selected_check_in,
        selected_check_out,
    )

_render_report()

st.markdown(
    f'<footer>{APP_COPY["footer"]} <a href="{LOGOS_PROFILE.url}" target="_blank">Hotel Logos Zakopane ↗</a></footer>',
    unsafe_allow_html=True,
)
