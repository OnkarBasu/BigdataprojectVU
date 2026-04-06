from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class GoingDarkConfig:
    min_gap_hours: float = 4.0
    min_distance_km: float = 1.0


@dataclass(slots=True, frozen=True)
class LoiteringConfig:
    max_distance_km: float = 0.5
    max_sog_knots: float = 1.0
    min_duration_hours: float = 2.0
    bucket_seconds: int = 5 * 60
    max_continuation_gap_seconds: int = 2 * 5 * 60
    minimum_port_radius_km: float = 0.0


@dataclass(slots=True, frozen=True)
class DraftChangeConfig:
    min_gap_hours: float = 2.0
    min_relative_change: float = 0.05
    minimum_port_radius_km: float = 0.0


@dataclass(slots=True, frozen=True)
class TeleportationConfig:
    max_speed_knots: float = 60.0
    d1_max_gap_hours: float = 0.5
    d2_max_gap_hours: float = 24.0
    min_gap_seconds: float = 30.0
    min_distance_km: float = 1.0
    d2_port_proximity_km: float = 15.0
    minimum_port_radius_km: float = 0.0


@dataclass(slots=True, frozen=True)
class SamplingConfig:
    ac_sampling_seconds: int = 5 * 60
    loitering_sampling_seconds: int = 20 * 60


@dataclass(slots=True, frozen=True)
class DetectionConfig:
    going_dark: GoingDarkConfig = field(default_factory=GoingDarkConfig)
    draft_change: DraftChangeConfig = field(default_factory=DraftChangeConfig)
    teleportation: TeleportationConfig = field(default_factory=TeleportationConfig)
    loitering: LoiteringConfig = field(default_factory=LoiteringConfig)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)


DEFAULT_DETECTION_CONFIG = DetectionConfig()
