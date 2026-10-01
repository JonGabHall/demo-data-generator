"""Synthetic asset taxonomy and type-level replacement-price assumptions.

The USD bands are planning estimates for demonstrations, not vendor quotes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import random


PRICEBOOK_VERSION = "asset-type-usd-v1"
PRICE_CURRENCY = "USD"
PRICE_BASIS = "Synthetic type-level planning bands; not vendor quotes"


CATEGORY_CODES = {
    "Building Services": "BLDG",
    "Clinical Equipment": "CLIN",
    "Communications Equipment": "COMM",
    "Diagnostic Equipment": "DIAG",
    "Electrical Equipment": "ELEC",
    "Fire and Life Safety": "FIRE",
    "Furniture": "FURN",
    "IT Equipment": "IT",
    "Plumbing Equipment": "PLMB",
    "Security Equipment": "SECU",
}

ASSET_TYPE_COST_BANDS = {
    "Building Services": {
        "AIR_HANDLING_UNIT": (25_000, 250_000),
        "BOILER": (20_000, 200_000),
        "BREAK_ROOM_APPLIANCE": (300, 5_000),
        "BUILDING_AUTOMATION_CONTROLLER": (3_000, 25_000),
        "CHEMICAL_DISPENSER": (250, 2_500),
        "CIRCULATION_PUMP": (2_500, 25_000),
        "COMMERCIAL_REFRIGERATOR": (1_500, 12_000),
        "MEDICAL_GAS_OUTLET": (300, 2_000),
        "ROOF_HVAC_UNIT": (15_000, 150_000),
        "ROOFTOP_HVAC_UNIT": (15_000, 150_000),
    },
    "Clinical Equipment": {
        "ANESTHESIA_MACHINE": (30_000, 120_000),
        "ELECTROSURGICAL_UNIT": (8_000, 40_000),
        "EXAM_TABLE": (1_000, 10_000),
        "HOSPITAL_BED": (5_000, 20_000),
        "INFUSION_PUMP": (2_000, 10_000),
        "LAB_REFRIGERATOR": (3_000, 25_000),
        "MEDICATION_REFRIGERATOR": (5_000, 20_000),
        "OPERATING_TABLE": (10_000, 100_000),
        "PATIENT_MONITOR": (2_000, 25_000),
        "PREP_MONITOR": (2_000, 25_000),
        "PREP_STRETCHER": (1_000, 5_000),
        "PROCEDURE_LIGHT": (5_000, 80_000),
        "PROCEDURE_TABLE": (2_000, 20_000),
        "RECOVERY_BED": (3_000, 15_000),
        "SPECIALTY_EXAM_TABLE": (2_000, 15_000),
        "SURGICAL_LIGHT": (8_000, 80_000),
        "THERAPY_EQUIPMENT": (2_000, 150_000),
        "THERAPY_TABLE": (1_000, 15_000),
        "TREATMENT_CHAIR": (1_000, 15_000),
        "VITAL_SIGNS_MONITOR": (1_500, 8_000),
        "WALL_DIAGNOSTIC_SET": (1_000, 8_000),
    },
    "Communications Equipment": {
        "ASSISTIVE_LISTENING_SYSTEM": (1_000, 8_000),
        "DIGITAL_SIGNAGE": (500, 5_000),
        "EMERGENCY_INTERCOM": (800, 5_000),
        "NURSE_CALL_CONSOLE": (3_000, 25_000),
        "NURSE_CALL_STATION": (500, 5_000),
        "PRESENTATION_DISPLAY": (800, 10_000),
        "VIDEO_CONFERENCING_SYSTEM": (2_000, 25_000),
        "WIRELESS_ACCESS_POINT": (150, 1_500),
    },
    "Diagnostic Equipment": {
        "DIAGNOSTIC_WORKSTATION": (3_000, 15_000),
        "IMAGING_MODALITY": (100_000, 1_500_000),
        "LAB_ANALYZER": (10_000, 300_000),
        "RADIATION_MONITOR": (500, 10_000),
    },
    "Electrical Equipment": {
        "AUTOMATIC_TRANSFER_SWITCH": (4_000, 100_000),
        "BACKUP_GENERATOR": (40_000, 350_000),
        "EMERGENCY_GENERATOR": (40_000, 350_000),
        "ELECTRICAL_METER": (300, 4_000),
        "ELEVATOR_CONTROL_PANEL": (15_000, 150_000),
        "EXTERIOR_LIGHT_FIXTURE": (200, 3_000),
        "COMMON_AREA_LIGHT_FIXTURE": (100, 1_500),
        "CORRIDOR_LIGHT_FIXTURE": (100, 1_000),
        "PANELBOARD": (1_000, 15_000),
        "PARKING_LIGHT_FIXTURE": (500, 5_000),
        "SWITCHGEAR": (10_000, 300_000),
        "UPS": (500, 50_000),
        "VARIABLE_FREQUENCY_DRIVE": (1_000, 30_000),
    },
    "Fire and Life Safety": {
        "DUCT_SMOKE_DETECTOR": (100, 700),
        "EMERGENCY_LIGHT": (80, 700),
        "EXIT_SIGN": (80, 500),
        "FIRE_ALARM_PANEL": (2_000, 30_000),
        "FIRE_ALARM_PULL_STATION": (75, 500),
        "FIRE_DAMPER": (400, 3_500),
        "FIRE_EXTINGUISHER_CABINET": (200, 1_500),
        "FIRE_SUPPRESSION_PANEL": (5_000, 50_000),
    },
    "Furniture": {
        "ERGONOMIC_CHAIR": (250, 1_500),
        "MEDICATION_STORAGE_CABINET": (500, 5_000),
        "OFFICE_FURNITURE": (250, 6_000),
        "RECEPTION_DESK": (800, 6_000),
        "RECORDS_STORAGE_SYSTEM": (500, 20_000),
        "SERVICE_COUNTER": (1_000, 10_000),
        "STAFF_LOCKER": (200, 1_000),
        "STORAGE_SHELVING": (300, 5_000),
    },
    "IT Equipment": {
        "CLINICAL_WORKSTATION": (1_500, 5_000),
        "MULTIFUNCTION_PRINTER": (300, 5_000),
        "NETWORK_RACK": (800, 8_000),
        "OFFICE_WORKSTATION": (1_000, 4_000),
        "PACS_WORKSTATION": (2_000, 12_000),
        "PHARMACY_WORKSTATION": (1_500, 6_000),
        "QUEUE_DISPLAY": (300, 2_500),
        "RECORDS_SCANNER": (500, 10_000),
        "RECORDS_WORKSTATION": (1_000, 4_000),
        "WORKSTATION": (1_000, 4_000),
    },
    "Plumbing Equipment": {
        "CLINICAL_HANDWASH_SINK": (1_000, 6_000),
        "HANDWASH_SINK": (700, 5_000),
        "LAB_SINK": (1_000, 8_000),
        "MOP_SINK": (500, 3_000),
        "RESTROOM_FIXTURE": (300, 5_000),
    },
    "Security Equipment": {
        "ACCESSIBLE_ENTRY_BUTTON": (150, 800),
        "ACCESS_CONTROL_PANEL": (1_500, 12_000),
        "ACCESS_CONTROL_READER": (250, 1_200),
        "ENVIRONMENTAL_SENSOR": (150, 2_000),
        "EXTERIOR_SECURITY_CAMERA": (500, 4_000),
        "PARKING_SECURITY_CAMERA": (500, 5_000),
        "SECURITY_CAMERA": (300, 5_000),
    },
}

WARRANTY_YEAR_RANGES = {
    "Building Services": (2, 5),
    "Clinical Equipment": (2, 4),
    "Communications Equipment": (1, 3),
    "Diagnostic Equipment": (2, 5),
    "Electrical Equipment": (2, 5),
    "Fire and Life Safety": (2, 5),
    "Furniture": (5, 10),
    "IT Equipment": (1, 3),
    "Plumbing Equipment": (2, 5),
    "Security Equipment": (2, 4),
}

ASSET_CLASS_VENDORS = {
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


@dataclass(frozen=True)
class AssetMetadata:
    category_code: str
    category_type: str
    subtype_code: str
    category_subtype: str
    replacement_cost: float
    purchase_date: date
    purchase_cost: float
    vendor: str
    warranty_expiration_date: date
    warranty_status: str
    annual_maintenance_cost: float
    risk_score: int
    risk_level: str


def _stable_bucket(identity: str, label: str, size: int) -> int:
    digest = hashlib.sha256(f"{label}|{identity}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def asset_taxonomy(asset_type: str, asset_class: str) -> dict[str, str]:
    """Return a stable project taxonomy for one supported asset type."""
    category_code = CATEGORY_CODES.get(asset_class)
    price_band = ASSET_TYPE_COST_BANDS.get(asset_class, {}).get(asset_type)
    if category_code is None or price_band is None:
        raise ValueError(f"No taxonomy and pricebook entry for {asset_class!r}/{asset_type!r}.")
    digest = hashlib.sha256(asset_type.encode("utf-8")).hexdigest()[:11].upper()
    special_words = {"hvac": "HVAC", "it": "IT", "pacs": "PACS", "ups": "UPS"}
    category_subtype = " ".join(
        special_words.get(word.lower(), word.title()) for word in asset_type.split("_")
    )
    return {
        "Category_Code": category_code,
        "Category_Type": asset_class,
        "Subtype_Code": f"ST-{digest}",
        "Category_Subtype": category_subtype,
    }


def replacement_cost_for(asset_type: str, asset_class: str, identity: str) -> float:
    """Sample a deterministic unit replacement estimate from its type band."""
    asset_taxonomy(asset_type, asset_class)
    lower, upper = ASSET_TYPE_COST_BANDS[asset_class][asset_type]
    randomizer = random.Random(f"asset-price-v1|{asset_type}|{identity}")
    return float(randomizer.randint(lower, upper))


def purchase_cost_for(replacement_cost: float, identity: str) -> float:
    fraction = 0.62 + _stable_bucket(identity, "purchase-fraction", 3001) / 10_000
    return round(replacement_cost * fraction, 2)


def purchase_date_for(commissioning_date: date, identity: str) -> date:
    lead_days = 14 + _stable_bucket(identity, "purchase-lead-days", 167)
    return commissioning_date - timedelta(days=lead_days)


def vendor_for(asset_class: str, identity: str) -> str:
    try:
        vendors = ASSET_CLASS_VENDORS[asset_class]
    except KeyError as error:
        raise ValueError(f"Unsupported asset class: {asset_class!r}.") from error
    return vendors[_stable_bucket(identity, "vendor", len(vendors))]


def warranty_expiration_for(
    commissioning_date: date, asset_class: str, identity: str
) -> date:
    try:
        minimum, maximum = WARRANTY_YEAR_RANGES[asset_class]
    except KeyError as error:
        raise ValueError(f"Unsupported asset class: {asset_class!r}.") from error
    years = minimum + _stable_bucket(identity, "warranty-years", maximum - minimum + 1)
    return commissioning_date + timedelta(days=round(years * 365.25))


def annual_maintenance_cost_for(
    replacement_cost: float, criticality: str, stage: str, condition: str
) -> float:
    criticality_rate = {"Low": 0.015, "Medium": 0.020, "High": 0.025, "Critical": 0.030}
    try:
        rate = criticality_rate[criticality]
    except KeyError as error:
        raise ValueError(f"Unsupported criticality: {criticality!r}.") from error
    if stage == "Retrofit/Replacement":
        rate += 0.01
    if condition != "Operational":
        rate += 0.005
    return round(replacement_cost * rate, 2)


def risk_score_for(
    criticality: str,
    condition: str,
    stage: str,
    overdue_days: int,
    maintenance_interval_days: int,
) -> int:
    criticality_score = {"Low": 10, "Medium": 25, "High": 40, "Critical": 55}
    condition_score = {"Operational": 0, "Maintenance Due": 20, "Offline Repair": 35}
    stage_score = {
        "Recently Installed": 0,
        "Within Service Life": 5,
        "Retrofit/Replacement": 20,
    }
    try:
        score = criticality_score[criticality]
        score += condition_score[condition]
        score += stage_score[stage]
    except KeyError as error:
        raise ValueError(f"Unsupported risk input: {error.args[0]!r}.") from error
    score += min(15, round(overdue_days / max(1, maintenance_interval_days) * 10))
    return min(100, score)


def risk_level_for(score: int) -> str:
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Moderate"
    return "Low"


def build_asset_metadata(
    asset_type: str,
    asset_class: str,
    identity: str,
    commissioning_date: date,
    criticality: str,
    condition: str,
    lifecycle_stage: str,
    overdue_days: int,
    maintenance_interval_days: int,
    reference_date: date,
) -> AssetMetadata:
    taxonomy = asset_taxonomy(asset_type, asset_class)
    replacement_cost = replacement_cost_for(asset_type, asset_class, identity)
    warranty_expiration_date = warranty_expiration_for(
        commissioning_date, asset_class, identity
    )
    score = risk_score_for(
        criticality,
        condition,
        lifecycle_stage,
        overdue_days,
        maintenance_interval_days,
    )
    return AssetMetadata(
        category_code=taxonomy["Category_Code"],
        category_type=taxonomy["Category_Type"],
        subtype_code=taxonomy["Subtype_Code"],
        category_subtype=taxonomy["Category_Subtype"],
        replacement_cost=replacement_cost,
        purchase_date=purchase_date_for(commissioning_date, identity),
        purchase_cost=purchase_cost_for(replacement_cost, identity),
        vendor=vendor_for(asset_class, identity),
        warranty_expiration_date=warranty_expiration_date,
        warranty_status=(
            "Active" if warranty_expiration_date >= reference_date else "Expired"
        ),
        annual_maintenance_cost=annual_maintenance_cost_for(
            replacement_cost, criticality, lifecycle_stage, condition
        ),
        risk_score=score,
        risk_level=risk_level_for(score),
    )


def estimated_repair_cost_for(replacement_cost: float, identity: str) -> float:
    fraction = 0.02 + _stable_bucket(identity, "inspection-repair-fraction", 7) / 100
    return round(replacement_cost * fraction, 2)


def repair_cost_for(replacement_cost: float, identity: str) -> float:
    fraction = 0.01 + _stable_bucket(identity, "repair-fraction", 8) / 100
    return round(replacement_cost * fraction, 2)