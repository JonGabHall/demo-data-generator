"""Profile-driven deterministic asset allocation independent of ArcPy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import random
from typing import Any
from uuid import UUID, uuid5


NAMESPACE = UUID("a95b7c8e-0521-4526-bc78-c3f6392dc078")


@dataclass(frozen=True)
class AssetTemplate:
    identifier: str
    asset_class: str
    quantity_min: int
    quantity_max: int
    criticality: str
    maintenance_interval_days: int
    dependencies: tuple[str, ...]
    placement_type: str | None = None


@dataclass(frozen=True)
class FacilityProfile:
    version: str
    room_uses: dict[str, tuple[AssetTemplate, ...]]
    room_use_aliases: dict[str, str]

    def templates_for(self, room_use: str) -> tuple[AssetTemplate, ...]:
        resolved_room_use = self.resolve_room_use(room_use)
        return self.room_uses[resolved_room_use]

    def resolve_room_use(self, room_use: str) -> str:
        normalized_room_use = _normalize_room_use(room_use)
        resolved_room_use = self.room_use_aliases.get(normalized_room_use, normalized_room_use)
        try:
            self.room_uses[resolved_room_use]
        except KeyError as error:
            supported = ", ".join(sorted(self.room_uses))
            raise UnmappedRoomUseError(
                f"Unmapped facility room use '{room_use}'. Add an explicit profile alias or use one of: {supported}"
            ) from error
        return resolved_room_use


class UnmappedRoomUseError(ValueError):
    """Raised when a source Units.USE_TYPE has no reviewed profile mapping."""


@dataclass(frozen=True)
class GeneratedAsset:
    asset_id: str
    unit_global_id: str
    room_use: str
    template_id: str
    asset_class: str
    business_id: str
    condition: str
    criticality: str
    commissioning_date: date
    next_maintenance_date: date
    system_dependencies: tuple[str, ...]
    placement_type: str | None = None


def load_facility_profile(profile_path: str | Path) -> FacilityProfile:
    """Load and validate a JSON facility rule pack."""
    data = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    room_uses: dict[str, tuple[AssetTemplate, ...]] = {}

    for room_use, template_data in data["room_uses"].items():
        templates = []
        for entry in template_data:
            quantity = entry["quantity"]
            if quantity["min"] < 0 or quantity["max"] < quantity["min"]:
                raise ValueError(f"Invalid quantity range for {entry['id']}")
            templates.append(
                AssetTemplate(
                    identifier=entry["id"],
                    asset_class=entry["asset_class"],
                    quantity_min=quantity["min"],
                    quantity_max=quantity["max"],
                    criticality=entry["criticality"],
                    maintenance_interval_days=entry["maintenance_interval_days"],
                    dependencies=tuple(entry["dependencies"]),
                    placement_type=entry.get("placement_type"),
                )
            )
        room_uses[_normalize_room_use(room_use)] = tuple(templates)

    aliases = {
        _normalize_room_use(alias): _normalize_room_use(target)
        for alias, target in data.get("room_use_aliases", {}).items()
    }
    for alias, target in aliases.items():
        if target not in room_uses:
            raise ValueError(f"Alias '{alias}' maps to unknown room use '{target}'")

    return FacilityProfile(
        version=data["version"], room_uses=room_uses, room_use_aliases=aliases
    )

def generate_assets(
    profile: FacilityProfile,
    unit_global_id: str,
    room_use: str,
    seed: int,
    reference_date: date = date(2026, 1, 1),
) -> list[GeneratedAsset]:
    """Generate deterministic, valid assets for one existing Indoors Unit."""
    resolved_room_use = profile.resolve_room_use(room_use)
    templates = profile.templates_for(resolved_room_use)
    randomizer = random.Random(f"{seed}|{profile.version}|{unit_global_id}|{resolved_room_use}")
    assets: list[GeneratedAsset] = []

    for template in templates:
        quantity = randomizer.randint(template.quantity_min, template.quantity_max)
        for sequence in range(1, quantity + 1):
            asset_id = str(uuid5(NAMESPACE, f"{seed}|{unit_global_id}|{template.identifier}|{sequence}"))
            age_days = randomizer.randint(90, 3650)
            commissioning_date = reference_date - timedelta(days=age_days)
            condition = _condition_for(randomizer, age_days)
            assets.append(
                GeneratedAsset(
                    asset_id=asset_id,
                    unit_global_id=unit_global_id,
                    room_use=resolved_room_use,
                    template_id=template.identifier,
                    asset_class=template.asset_class,
                    business_id=f"DMA-{template.identifier}-{asset_id[:8].upper()}",
                    condition=condition,
                    criticality=template.criticality,
                    commissioning_date=commissioning_date,
                    next_maintenance_date=commissioning_date
                    + timedelta(days=template.maintenance_interval_days),
                    system_dependencies=template.dependencies,
                    placement_type=template.placement_type,
                )
            )
    return assets


def _normalize_room_use(room_use: str) -> str:
    return "_".join(room_use.strip().upper().replace("-", " ").split())


def _condition_for(randomizer: random.Random, age_days: int) -> str:
    maintenance_weight = 10 if age_days > 1825 else 4
    roll = randomizer.randrange(100)
    if roll < maintenance_weight:
        return "Maintenance Due"
    if roll < maintenance_weight + 2:
        return "Offline Repair"
    return "Operational"
