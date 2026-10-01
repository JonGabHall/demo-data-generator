"""Deterministic lifecycle and maintenance-history planning for generated assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import random
from typing import Protocol

from .asset_catalog import (
    annual_maintenance_cost_for,
    asset_taxonomy,
    estimated_repair_cost_for,
    purchase_cost_for,
    purchase_date_for,
    repair_cost_for,
    replacement_cost_for,
    risk_level_for,
    risk_score_for,
    warranty_expiration_for,
)


EXPECTED_LIFE_RANGES = {
    "Building Services": (15, 25),
    "Clinical Equipment": (8, 12),
    "Communications Equipment": (6, 10),
    "Diagnostic Equipment": (8, 12),
    "Electrical Equipment": (20, 30),
    "Fire and Life Safety": (12, 20),
    "Furniture": (10, 15),
    "IT Equipment": (4, 8),
    "Plumbing Equipment": (20, 30),
    "Security Equipment": (7, 12),
}

MANUFACTURERS = {
    "Building Services": ("Trane", "Carrier", "Johnson Controls"),
    "Clinical Equipment": ("GE HealthCare", "Philips", "Stryker"),
    "Communications Equipment": ("Cisco", "Poly", "Motorola Solutions"),
    "Diagnostic Equipment": ("Siemens Healthineers", "Canon Medical", "Abbott"),
    "Electrical Equipment": ("Eaton", "Schneider Electric", "Siemens"),
    "Fire and Life Safety": ("Honeywell", "Simplex", "Siemens"),
    "Furniture": ("Steelcase", "Herman Miller", "Haworth"),
    "IT Equipment": ("Dell", "HP", "Lenovo"),
    "Plumbing Equipment": ("Kohler", "Sloan", "Zurn"),
    "Security Equipment": ("Axis", "Bosch", "HID Global"),
}

VENDORS = {
    "Building Services": ("Grainger", "Ferguson Facilities Supply", "Johnson Controls"),
    "Clinical Equipment": ("Cardinal Health", "Medline Industries", "McKesson"),
    "Communications Equipment": ("CDW-G", "SHI International", "Presidio"),
    "Diagnostic Equipment": ("Cardinal Health", "Henry Schein", "McKesson"),
    "Electrical Equipment": ("Graybar", "Grainger", "WESCO"),
    "Fire and Life Safety": ("Convergint", "Johnson Controls", "Siemens Smart Infrastructure"),
    "Furniture": ("CORT", "Kimball International", "Steelcase Health"),
    "IT Equipment": ("CDW-G", "Insight", "SHI International"),
    "Plumbing Equipment": ("Ferguson", "Grainger", "Winsupply"),
    "Security Equipment": ("Convergint", "Presidio", "Securitas Technology"),
}

class NarrativeProvider(Protocol):
    def narrate(self, record_type: str, facts: dict[str, object], fallback: str) -> str:
        """Return one short narrative based only on the supplied facts."""
        ...


@dataclass(frozen=True)
class AssetSeed:
    asset_id: str
    global_id: str
    asset_type: str
    asset_class: str
    criticality: str
    unit_id: str
    level_id: str
    facility_id: str
    site_id: str
    maintenance_interval_days: int


@dataclass(frozen=True)
class EnrichmentConfig:
    reference_date: date = date(2026, 9, 28)
    inspection_start: date = date(2021, 9, 28)
    inspection_end: date = date(2026, 3, 28)
    seed: int = 3141
    repair_rate: float = 0.27
    historical_work_order_rate: float = 0.45
    active_work_order_rate: float = 0.05

    def __post_init__(self) -> None:
        if not self.inspection_start <= self.inspection_end < self.reference_date:
            raise ValueError("Inspection dates must end before the reference date.")
        for name in (
            "repair_rate",
            "historical_work_order_rate",
            "active_work_order_rate",
        ):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1.")


@dataclass(frozen=True)
class LifecycleUpdate:
    asset_id: str
    asset_type: str
    asset_class: str
    facility_id: str
    site_id: str
    condition: str
    commissioning_date: date
    next_maintenance_date: date
    make: str
    model: str
    serial: str
    owner: str
    lifecycle_stage: str
    expected_life_years: int
    asset_age_years: float
    remaining_life_years: float
    replacement_due_date: date
    replacement_year: int
    last_inspection_date: date
    overdue_days: int
    estimated_replacement_cost: float
    vendor: str
    purchase_date: date
    purchase_cost: float
    warranty_expiration_date: date
    warranty_status: str
    maintenance_interval_days: int
    annual_maintenance_cost: float
    risk_score: int
    risk_level: str
    category_code: str
    category_type: str
    subtype_code: str
    category_subtype: str


@dataclass(frozen=True)
class InspectionRecord:
    asset_global_id: str
    asset_id: str
    asset_type: str
    inspection_date: date
    inspector: str
    condition_rating: str
    repair_needed: str
    notes: str
    estimated_repair_cost: float | None
    repair_type: str


@dataclass(frozen=True)
class RepairRecord:
    asset_global_id: str
    asset_id: str
    asset_type: str
    repair_date: date
    technician: str
    repair_type: str
    notes: str
    repair_cost: float


@dataclass(frozen=True)
class WorkOrderRecord:
    asset_global_id: str
    work_order_id: str
    request_type: str
    request_date: date
    description: str
    asset_id: str
    asset_type: str
    unit_id: str
    level_id: str
    facility_id: str
    facility_name: str
    assignee: str
    status: str


@dataclass(frozen=True)
class EnrichmentPlan:
    lifecycle: tuple[LifecycleUpdate, ...]
    inspections: tuple[InspectionRecord, ...]
    repairs: tuple[RepairRecord, ...]
    work_orders: tuple[WorkOrderRecord, ...]


def build_enrichment_plan(
    assets: list[AssetSeed],
    config: EnrichmentConfig = EnrichmentConfig(),
    narrator: NarrativeProvider | None = None,
    facility_name: str = "Vertex Medical Center",
) -> EnrichmentPlan:
    """Build deterministic lifecycle updates and related records for existing assets."""
    if not assets:
        raise ValueError("At least one asset is required.")
    asset_ids = [asset.asset_id for asset in assets]
    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("Asset IDs must be unique.")
    unknown_classes = sorted({asset.asset_class for asset in assets} - EXPECTED_LIFE_RANGES.keys())
    if unknown_classes:
        raise ValueError(f"Unsupported asset classes: {', '.join(unknown_classes)}")

    replacement_ids = _select_exact(assets, 0.30, "replacement", config.seed)
    recent_ids = _select_exact(
        [asset for asset in assets if asset.asset_id not in replacement_ids],
        0.20 * len(assets) / max(1, len(assets) - len(replacement_ids)),
        "recent",
        config.seed,
    )
    repair_ids = _select_exact(assets, config.repair_rate, "repair", config.seed)
    historical_ids = _select_exact(
        assets, config.historical_work_order_rate, "historical-work-order", config.seed
    )
    active_ids = _select_exact(assets, config.active_work_order_rate, "active-work-order", config.seed)

    lifecycle: list[LifecycleUpdate] = []
    inspections: list[InspectionRecord] = []
    repairs: list[RepairRecord] = []
    work_orders: list[WorkOrderRecord] = []
    for asset in sorted(assets, key=lambda item: item.asset_id):
        stage = (
            "Retrofit/Replacement"
            if asset.asset_id in replacement_ids
            else "Recently Installed"
            if asset.asset_id in recent_ids
            else "Within Service Life"
        )
        randomizer = random.Random(f"enrichment|{config.seed}|{asset.asset_id}")
        life_min, life_max = EXPECTED_LIFE_RANGES[asset.asset_class]
        life_years = randomizer.randint(life_min, life_max)
        life_days = round(life_years * 365.25)
        if stage == "Recently Installed":
            age_days = randomizer.randint(184, min(730, round(life_days * 0.25)))
        elif stage == "Within Service Life":
            age_days = randomizer.randint(round(life_days * 0.20), round(life_days * 0.75))
        else:
            age_days = randomizer.randint(round(life_days * 0.80), round(life_days * 1.05))
        commissioning_date = config.reference_date - timedelta(days=age_days)
        replacement_due_date = commissioning_date + timedelta(days=life_days)
        inspection_lower = max(config.inspection_start, commissioning_date)
        inspection_span = (config.inspection_end - inspection_lower).days
        recency_window = min(inspection_span, max(90, asset.maintenance_interval_days * 2))
        last_inspection_date = config.inspection_end - timedelta(
            days=randomizer.randint(0, max(0, recency_window))
        )
        last_inspection_date = max(last_inspection_date, inspection_lower)
        next_maintenance_date = last_inspection_date + timedelta(
            days=asset.maintenance_interval_days
        )
        overdue_days = max(0, (config.reference_date - next_maintenance_date).days)

        condition_roll = randomizer.randrange(100)
        if asset.asset_id in active_ids:
            condition = "Offline Repair" if condition_roll < 18 else "Maintenance Due"
        elif stage == "Retrofit/Replacement":
            condition = "Maintenance Due" if condition_roll < 32 else "Operational"
        else:
            condition = "Maintenance Due" if condition_roll < 8 else "Operational"
        manufacturers = MANUFACTURERS[asset.asset_class]
        make = manufacturers[randomizer.randrange(len(manufacturers))]
        replacement_cost = replacement_cost_for(
            asset.asset_type, asset.asset_class, asset.asset_id
        )
        vendors = VENDORS[asset.asset_class]
        vendor = vendors[randomizer.randrange(len(vendors))]
        purchase_date = purchase_date_for(commissioning_date, asset.asset_id)
        purchase_cost = purchase_cost_for(replacement_cost, asset.asset_id)
        warranty_expiration_date = warranty_expiration_for(
            commissioning_date, asset.asset_class, asset.asset_id
        )
        warranty_status = (
            "Active" if warranty_expiration_date >= config.reference_date else "Expired"
        )
        annual_maintenance_cost = annual_maintenance_cost_for(
            replacement_cost, asset.criticality, stage, condition
        )
        risk_score = risk_score_for(
            asset.criticality,
            condition,
            stage,
            overdue_days,
            asset.maintenance_interval_days,
        )
        taxonomy = asset_taxonomy(asset.asset_type, asset.asset_class)
        lifecycle_record = LifecycleUpdate(
            asset_id=asset.asset_id,
            asset_type=asset.asset_type,
            asset_class=asset.asset_class,
            facility_id=asset.facility_id,
            site_id=asset.site_id,
            condition=condition,
            commissioning_date=commissioning_date,
            next_maintenance_date=next_maintenance_date,
            make=make,
            model=f"{asset.asset_type[:18]}-{100 + randomizer.randrange(900)}",
            serial=hashlib.sha256(f"serial|{asset.asset_id}".encode()).hexdigest()[:16].upper(),
            owner=_owner_for(asset.asset_class),
            lifecycle_stage=stage,
            expected_life_years=life_years,
            asset_age_years=round(age_days / 365.25, 1),
            remaining_life_years=round(
                (replacement_due_date - config.reference_date).days / 365.25, 1
            ),
            replacement_due_date=replacement_due_date,
            replacement_year=replacement_due_date.year,
            last_inspection_date=last_inspection_date,
            overdue_days=overdue_days,
            estimated_replacement_cost=replacement_cost,
            vendor=vendor,
            purchase_date=purchase_date,
            purchase_cost=purchase_cost,
            warranty_expiration_date=warranty_expiration_date,
            warranty_status=warranty_status,
            maintenance_interval_days=asset.maintenance_interval_days,
            annual_maintenance_cost=annual_maintenance_cost,
            risk_score=risk_score,
            risk_level=risk_level_for(risk_score),
            category_code=taxonomy["Category_Code"],
            category_type=taxonomy["Category_Type"],
            subtype_code=taxonomy["Subtype_Code"],
            category_subtype=taxonomy["Category_Subtype"],
        )
        lifecycle.append(lifecycle_record)
        inspections.extend(
            _inspection_history(asset, lifecycle_record, config, narrator)
        )

        if asset.asset_id in repair_ids:
            repair_date = min(
                config.reference_date,
                last_inspection_date + timedelta(days=7 + _stable_number(asset.asset_id, 75)),
            )
            fallback = f"Condition-based service completed for {asset.asset_type}."
            repairs.append(
                RepairRecord(
                    asset.global_id,
                    asset.asset_id,
                    asset.asset_type,
                    repair_date,
                    "Vertex Clinical Engineering",
                    "Corrective Repair" if condition != "Operational" else "Preventive Service",
                    _narrate(narrator, "repair", _facts(asset, condition, stage), fallback),
                    repair_cost_for(replacement_cost, asset.asset_id),
                )
            )
        if asset.asset_id in historical_ids:
            request_date = min(
                config.reference_date,
                last_inspection_date + timedelta(days=1 + _stable_number(asset.asset_id, 60)),
            )
            fallback = f"Completed scheduled maintenance for {asset.asset_type}."
            work_orders.append(
                _work_order(
                    asset,
                    facility_name,
                    request_date,
                    "Completed",
                    "Preventive Maintenance",
                    "H",
                    _narrate(narrator, "work_order", _facts(asset, condition, stage), fallback),
                )
            )
        if asset.asset_id in active_ids:
            request_date = config.inspection_end + timedelta(
                days=1 + _stable_number(asset.asset_id, (config.reference_date - config.inspection_end).days)
            )
            status = ("Open", "Assigned", "In Progress", "On Hold")[
                _stable_number(asset.asset_id, 4)
            ]
            fallback = f"Investigate {condition.lower()} condition reported for {asset.asset_type}."
            work_orders.append(
                _work_order(
                    asset,
                    facility_name,
                    request_date,
                    status,
                    "Corrective Maintenance",
                    "A",
                    _narrate(narrator, "work_order", _facts(asset, condition, stage), fallback),
                )
            )

    return EnrichmentPlan(
        tuple(lifecycle), tuple(inspections), tuple(repairs), tuple(work_orders)
    )


def _inspection_history(
    asset: AssetSeed,
    lifecycle: LifecycleUpdate,
    config: EnrichmentConfig,
    narrator: NarrativeProvider | None,
) -> list[InspectionRecord]:
    records = []
    inspection_date = lifecycle.last_inspection_date
    earliest = max(config.inspection_start, lifecycle.commissioning_date)
    history_index = 0
    cadence = asset.maintenance_interval_days
    if asset.criticality in {"High", "Critical"}:
        cadence = max(90, cadence // 2)
    while inspection_date >= earliest and history_index < 6:
        latest = history_index == 0
        rating = (
            {
                "Operational": "Good" if _stable_number(asset.asset_id, 5) else "Excellent",
                "Maintenance Due": "Fair",
                "Offline Repair": "Poor",
            }[lifecycle.condition]
            if latest
            else "Good"
        )
        repair_needed = "Y" if latest and lifecycle.condition != "Operational" else "N"
        fallback = (
            f"Latest condition inspection rated {rating.lower()} for {asset.asset_type}."
            if latest
            else f"Scheduled preventive inspection completed for {asset.asset_type}."
        )
        records.append(
            InspectionRecord(
                asset.global_id,
                asset.asset_id,
                asset.asset_type,
                inspection_date,
                "Avery Morgan" if history_index % 2 == 0 else "Jordan Lee",
                rating,
                repair_needed,
                _narrate(
                    narrator,
                    "inspection",
                    {
                        **_facts(
                            asset,
                            lifecycle.condition,
                            lifecycle.lifecycle_stage,
                        ),
                        "condition_rating": rating,
                        "repair_needed": repair_needed,
                    },
                    fallback,
                )
                if latest
                else fallback,
                estimated_repair_cost_for(
                    lifecycle.estimated_replacement_cost, asset.asset_id
                )
                if repair_needed == "Y"
                else None,
                "Corrective" if repair_needed == "Y" else "Preventive",
            )
        )
        history_index += 1
        jitter = _stable_number(f"{asset.asset_id}|{history_index}", 61) - 30
        inspection_date -= timedelta(days=max(60, cadence + jitter))
    return records


def _work_order(
    asset: AssetSeed,
    facility_name: str,
    request_date: date,
    status: str,
    request_type: str,
    suffix: str,
    description: str,
) -> WorkOrderRecord:
    digest = hashlib.sha1(f"{suffix}|{asset.asset_id}".encode()).hexdigest()[:12].upper()
    return WorkOrderRecord(
        asset.global_id,
        f"WO-{suffix}-{digest}",
        request_type,
        request_date,
        description,
        asset.asset_id,
        asset.asset_type,
        asset.unit_id,
        asset.level_id,
        asset.facility_id,
        facility_name,
        "Vertex Clinical Engineering",
        status,
    )


def _select_exact(assets: list[AssetSeed], rate: float, label: str, seed: int) -> set[str]:
    count = round(len(assets) * rate)
    ranked = sorted(
        assets,
        key=lambda asset: _stable_number(f"{seed}|{label}|{asset.asset_id}", 10**15),
        reverse=True,
    )
    return {asset.asset_id for asset in ranked[:count]}


def _stable_number(value: str, modulo: int) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest()[:16], 16) % modulo


def _owner_for(asset_class: str) -> str:
    if asset_class in {"Clinical Equipment", "Diagnostic Equipment"}:
        return "Clinical Engineering"
    if asset_class in {"IT Equipment", "Communications Equipment", "Security Equipment"}:
        return "Digital Infrastructure"
    if asset_class == "Furniture":
        return "Workplace Services"
    return "Facilities Engineering"


def _risk_score(
    asset: AssetSeed, condition: str, stage: str, overdue_days: int
) -> int:
    score = {
        "Low": 10,
        "Medium": 25,
        "High": 40,
        "Critical": 55,
    }[asset.criticality]
    score += {
        "Operational": 0,
        "Maintenance Due": 20,
        "Offline Repair": 35,
    }[condition]
    score += {
        "Recently Installed": 0,
        "Within Service Life": 5,
        "Retrofit/Replacement": 20,
    }[stage]
    score += min(15, round(overdue_days / max(1, asset.maintenance_interval_days) * 10))
    return min(100, score)


def _risk_level(score: int) -> str:
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Moderate"
    return "Low"


def _facts(asset: AssetSeed, condition: str, stage: str) -> dict[str, object]:
    return {
        "asset_type": asset.asset_type,
        "asset_class": asset.asset_class,
        "criticality": asset.criticality,
        "condition": condition,
        "lifecycle_stage": stage,
    }


def _narrate(
    narrator: NarrativeProvider | None,
    record_type: str,
    facts: dict[str, object],
    fallback: str,
) -> str:
    return narrator.narrate(record_type, facts, fallback) if narrator else fallback