from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class HotelProfile:
    name: str
    description: str
    url: str


@dataclass(frozen=True, slots=True)
class HotelOffer:
    name: str
    nightly_price: float
    total_price: float
    description: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    score: int
    reason: str


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    offers: list[HotelOffer]
    logos_nightly_price: float
    logos_total_price: float
    is_live: bool
    warnings: list[str] = field(default_factory=list)
