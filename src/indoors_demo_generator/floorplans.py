"""Deterministic synthetic floor plans for non-reference facilities."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math


@dataclass(frozen=True)
class Rectangle:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    @property
    def area(self) -> float:
        return self.width * self.height

    def inset(self, distance: float) -> "Rectangle":
        if distance < 0 or self.width <= distance * 2 or self.height <= distance * 2:
            raise ValueError("Inset must leave a positive floor-plan area.")
        return Rectangle(
            self.xmin + distance,
            self.ymin + distance,
            self.xmax - distance,
            self.ymax - distance,
        )

    def contains(self, other: "Rectangle") -> bool:
        tolerance = 1e-9
        return (
            self.xmin - tolerance <= other.xmin
            and self.ymin - tolerance <= other.ymin
            and self.xmax + tolerance >= other.xmax
            and self.ymax + tolerance >= other.ymax
        )

    def overlaps(self, other: "Rectangle") -> bool:
        overlap_width = min(self.xmax, other.xmax) - max(self.xmin, other.xmin)
        overlap_height = min(self.ymax, other.ymax) - max(self.ymin, other.ymin)
        tolerance = 1e-9
        return overlap_width > tolerance and overlap_height > tolerance


@dataclass(frozen=True)
class PlannedUnit:
    unit_id: str
    level_id: str
    use_type: str
    name: str
    rectangle: Rectangle


@dataclass(frozen=True)
class PlannedLevel:
    level_id: str
    name: str
    short_name: str
    level_number: int
    vertical_order: int
    rectangle: Rectangle
    units: tuple[PlannedUnit, ...]


@dataclass(frozen=True)
class FacilityFloorPlan:
    facility_id: str
    facility_name: str
    facility_kind: str
    rotation_degrees: float
    footprint: Rectangle
    levels: tuple[PlannedLevel, ...]

    @property
    def units(self) -> tuple[PlannedUnit, ...]:
        return tuple(unit for level in self.levels for unit in level.units)


_HOSPITAL_PROGRAMS = {
    "B": (
        "MECHANICAL_ROOM",
        "ELECTRICAL_ROOM",
        "TELECOM_ROOM",
        "HVAC_SHAFT",
        "JANITORIAL_ROOM",
    ),
    "1": (
        "EXAM_ROOM",
        "EXAM_ROOM",
        "RECEPTION",
        "EXAM_ROOM",
        "IMAGING_ROOM",
        "EXAM_ROOM",
    ),
    "2": (
        "OPERATING_ROOM",
        "EXAM_ROOM",
        "PATIENT_ROOM",
        "OPERATING_ROOM",
        "PATIENT_ROOM",
        "IMAGING_ROOM",
    ),
    "3": (
        "PATIENT_ROOM",
        "PATIENT_ROOM",
        "EXAM_ROOM",
        "PATIENT_ROOM",
        "PATIENT_ROOM",
        "IMAGING_ROOM",
    ),
}

_OFFICE_PROGRAM = (
    "OFFICE",
    "OFFICE",
    "OFFICE",
    "MEETING_ROOM",
    "STAFF_SUPPORT",
    "OFFICE",
    "PUBLIC_SERVICE_COUNTER",
    "SECURE_RECORDS_ROOM",
)

_DISPLAY_NAMES = {
    "ELECTRICAL_ROOM": "Electrical Room",
    "EXAM_ROOM": "Exam Room",
    "HALLWAY": "Main Corridor",
    "HVAC_SHAFT": "HVAC Shaft",
    "IMAGING_ROOM": "Imaging Room",
    "IT_SERVER_ROOM": "IT Server Room",
    "JANITORIAL_ROOM": "Janitorial Room",
    "MECHANICAL_ROOM": "Mechanical Room",
    "MEETING_ROOM": "Meeting Room",
    "OFFICE": "Office",
    "OPERATING_ROOM": "Operating Room",
    "PATIENT_ROOM": "Patient Room",
    "PUBLIC_SERVICE_COUNTER": "Public Service Counter",
    "RECEPTION": "Reception",
    "RESTROOM": "Restroom",
    "SECURE_RECORDS_ROOM": "Secure Records Room",
    "STAFF_SUPPORT": "Staff Support",
    "STAIRWELL": "Stairwell",
    "STORAGE": "Storage",
    "TELECOM_ROOM": "Telecom Room",
    "VERTICAL_TRANSPORT": "Elevator Lobby",
}


def create_facility_floor_plan(
    facility_id: str,
    facility_name: str,
    facility_kind: str,
) -> FacilityFloorPlan:
    """Create a distinct, repeatable corridor-and-room plan from a facility key."""
    if facility_kind not in {"hospital", "office"}:
        raise ValueError(f"Unsupported facility kind: {facility_kind}")

    stable = _stable_number(facility_id)
    if facility_kind == "hospital":
        width = 82.0 + stable % 19
        depth = 28.0 + (stable // 19) % 7
        rotation = float((stable // 133) % 6 * 7 - 14)
        level_specs = (
            ("B", "Basement", "F0", 0, -1, 0.0),
            ("1", "Floor 1", "F1", 1, 0, 0.0),
            ("2", "Floor 2", "F2", 2, 1, 1.0),
            ("3", "Floor 3", "F3", 3, 2, 2.0),
            ("R", "Roof", "Roof", 4, 3, 1.0),
        )
        bay_width = 5.8
        corridor_width = 4.2
    else:
        width = 94.0 + stable % 17
        depth = 25.0 + (stable // 17) % 6
        rotation = float((stable // 102) % 5 * 6 - 12)
        level_specs = tuple(
            (str(number), f"Floor {number}", f"F{number}", number, number - 1, min(2.0, (number - 1) * 0.35))
            for number in range(1, 8)
        )
        bay_width = 5.4
        corridor_width = 3.6

    footprint = Rectangle(-width / 2, -depth / 2, width / 2, depth / 2)
    levels: list[PlannedLevel] = []
    unit_sequence = 0
    for suffix, level_name, short_name, level_number, vertical_order, inset in level_specs:
        level_id = f"{facility_id}{suffix}"
        level_rectangle = footprint.inset(inset) if inset else footprint
        if suffix == "R":
            units: tuple[PlannedUnit, ...] = ()
        else:
            units, unit_sequence = _plan_level_units(
                facility_id,
                level_id,
                suffix,
                facility_kind,
                level_rectangle,
                bay_width,
                corridor_width,
                unit_sequence,
            )
        levels.append(
            PlannedLevel(
                level_id,
                level_name,
                short_name,
                level_number,
                vertical_order,
                level_rectangle,
                units,
            )
        )

    plan = FacilityFloorPlan(
        facility_id,
        facility_name,
        facility_kind,
        rotation,
        footprint,
        tuple(levels),
    )
    validate_floor_plan(plan)
    return plan


def validate_floor_plan(plan: FacilityFloorPlan) -> None:
    """Reject duplicate, overlapping, out-of-bounds, or implausibly small rooms."""
    unit_ids = [unit.unit_id for unit in plan.units]
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError(f"{plan.facility_id} floor plan contains duplicate Unit IDs.")
    if not plan.units:
        raise ValueError(f"{plan.facility_id} floor plan contains no Units.")

    for level in plan.levels:
        if not plan.footprint.contains(level.rectangle):
            raise ValueError(f"{level.level_id} extends outside the facility footprint.")
        for unit in level.units:
            if not level.rectangle.contains(unit.rectangle):
                raise ValueError(f"{unit.unit_id} extends outside {level.level_id}.")
            if unit.rectangle.area < 12.0:
                raise ValueError(f"{unit.unit_id} is smaller than 12 square map units.")
        for index, unit in enumerate(level.units):
            for other in level.units[index + 1 :]:
                if unit.rectangle.overlaps(other.rectangle):
                    raise ValueError(
                        f"{unit.unit_id} overlaps {other.unit_id} on {level.level_id}."
                    )


def unit_program_attributes(use_type: str) -> dict[str, int | str | None]:
    """Return generated Indoors Unit attributes for a room program."""
    return {
        "SCHEDULE_EMAIL": None,
        "AREA_ID": None,
        "ASSIGNMENT_TYPE": "none",
        "HEIGHT_RELATIVE": 4.5,
        "RESERVATION_METHOD": 0,
        "MacDockingStation": int(
            use_type in {"OFFICE", "PUBLIC_SERVICE_COUNTER", "RECEPTION", "STAFF_SUPPORT"}
        ),
        "DualMonitor": int(use_type in {"OFFICE", "PUBLIC_SERVICE_COUNTER"}),
        "Locker": int(use_type == "STAFF_SUPPORT"),
        "SitStandDesk": int(use_type in {"OFFICE", "PUBLIC_SERVICE_COUNTER"}),
        "Whiteboard": int(use_type in {"EXAM_ROOM", "MEETING_ROOM", "OPERATING_ROOM"}),
        "VideoConferencing": int(use_type == "MEETING_ROOM"),
        "WaterCooler": int(use_type in {"RECEPTION", "STAFF_SUPPORT"}),
        "Projector": int(use_type == "MEETING_ROOM"),
        "TrashCan": int(
            use_type
            not in {
                "ELECTRICAL_ROOM",
                "HALLWAY",
                "HVAC_SHAFT",
                "MECHANICAL_ROOM",
                "STAIRWELL",
                "TELECOM_ROOM",
                "VERTICAL_TRANSPORT",
            }
        ),
    }


def _plan_level_units(
    facility_id: str,
    level_id: str,
    level_suffix: str,
    facility_kind: str,
    bounds: Rectangle,
    bay_width: float,
    corridor_width: float,
    unit_sequence: int,
) -> tuple[tuple[PlannedUnit, ...], int]:
    bay_count = max(8, math.floor(bounds.width / bay_width))
    actual_bay_width = bounds.width / bay_count
    corridor_ymin = -corridor_width / 2
    corridor_ymax = corridor_width / 2
    if corridor_ymin <= bounds.ymin or corridor_ymax >= bounds.ymax:
        raise ValueError(f"{level_id} is too shallow for a central corridor.")

    room_rectangles: list[Rectangle] = []
    for side_ymin, side_ymax in (
        (bounds.ymin, corridor_ymin),
        (corridor_ymax, bounds.ymax),
    ):
        for bay_index in range(bay_count):
            xmin = bounds.xmin + bay_index * actual_bay_width
            room_rectangles.append(
                Rectangle(xmin, side_ymin, xmin + actual_bay_width, side_ymax)
            )

    units: list[PlannedUnit] = []
    total_rooms = len(room_rectangles)
    for room_index, rectangle in enumerate(room_rectangles):
        unit_sequence += 1
        use_type = _room_use(facility_kind, level_suffix, room_index, total_rooms)
        units.append(
            PlannedUnit(
                f"{facility_id}-U-{unit_sequence:04d}",
                level_id,
                use_type,
                _room_name(use_type, level_suffix, room_index + 1),
                rectangle,
            )
        )

    unit_sequence += 1
    units.append(
        PlannedUnit(
            f"{facility_id}-U-{unit_sequence:04d}",
            level_id,
            "HALLWAY",
            f"{_level_designator(level_suffix)} Main Corridor",
            Rectangle(bounds.xmin, corridor_ymin, bounds.xmax, corridor_ymax),
        )
    )
    return tuple(units), unit_sequence


def _room_use(
    facility_kind: str,
    level_suffix: str,
    room_index: int,
    total_rooms: int,
) -> str:
    if room_index in {0, total_rooms // 2}:
        return "STAIRWELL"
    if room_index in {total_rooms - 1, total_rooms // 2 - 1}:
        return "VERTICAL_TRANSPORT" if facility_kind == "office" else "STAIRWELL"
    if facility_kind == "office":
        office_services = {
            1: "RESTROOM",
            2: "JANITORIAL_ROOM",
            total_rooms // 2 + 1: "IT_SERVER_ROOM",
            total_rooms // 2 + 2: "ELECTRICAL_ROOM",
        }
        return office_services.get(room_index, _OFFICE_PROGRAM[room_index % len(_OFFICE_PROGRAM)])

    hospital_services = {
        1: "JANITORIAL_ROOM",
        total_rooms // 2 + 1: "ELECTRICAL_ROOM",
        total_rooms // 2 + 2: "TELECOM_ROOM",
    }
    if room_index in hospital_services:
        return hospital_services[room_index]
    program = _HOSPITAL_PROGRAMS[level_suffix]
    return program[room_index % len(program)]


def _room_name(use_type: str, level_suffix: str, room_number: int) -> str:
    return f"{_level_designator(level_suffix)} {_DISPLAY_NAMES[use_type]} {room_number:02d}"


def _level_designator(level_suffix: str) -> str:
    return "B" if level_suffix == "B" else f"L{level_suffix}"


def _stable_number(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)
