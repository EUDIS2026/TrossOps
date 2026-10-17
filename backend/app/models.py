"""Shared domain contract. The frontend `src/contracts/*.ts` mirrors these models field for field.
Everything here is synthetic scenario content unless `sourceKind` says otherwise."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

SourceKind = Literal["observed", "simulated", "inferred", "predicted", "planned", "public", "unknown"]
AltitudeDatum = Literal["WGS84_ELLIPSOID", "MSL", "AGL", "UNKNOWN"]
EntityKind = Literal[
    "fixed_wing", "helicopter", "multirotor", "ground_vehicle", "vessel",
    "personnel", "facility", "infrastructure", "unknown", "formation",
]
Domain = Literal["air", "land", "sea", "site", "infra", "unknown"]
Affiliation = Literal["own", "allied", "civil", "unknown", "hostile_suspected"]
Condition = Literal["normal", "degraded", "unavailable", "unknown"]
Severity = Literal["info", "advisory", "warning", "critical"]

Channel = Literal[
    "field_report",          # individual soldier / patrol
    "unit_sitrep",           # company / battalion situation report
    "logistics_report",      # supply, fuel, ammunition, transport
    "maintenance_log",       # workshop and fault records
    "sensor_detection",      # radar / sonar / EO sensor fusion text
    "intel_report",          # intelligence assessment
    "civil_emergency",       # 112 / county emergency services
    "weather_advisory",      # SMHI public warnings
    "infrastructure_status", # power, telecom, transport operators
    "public_news",           # open-source media
    "cyber_alert",           # CERT / network defence
    "command_directive",     # regional / joint command
    "allied_liaison",        # partner nation liaison officer
    "head_of_state_directive",
    "police_event",          # Polisen public events (real feed, municipality-level positions)
    "crisis_info",           # Krisinformation.se public crisis messages
]
AuthorLevel = Literal[
    "soldier", "platoon", "company", "battalion", "brigade", "regional", "joint", "national",
    "civil_authority", "operator", "sensor", "media", "allied", "head_of_state",
]


class GeoPosition(BaseModel):
    longitudeDeg: float = Field(ge=-180, le=180)
    latitudeDeg: float = Field(ge=-90, le=90)
    altitudeM: float | None = None
    altitudeDatum: AltitudeDatum = "UNKNOWN"
    horizontalAccuracyM: float | None = None


class Kinematics(BaseModel):
    headingDeg: float | None = None
    speedMps: float | None = None
    pitchDeg: float = 0.0
    bankDeg: float = 0.0
    phase: str | None = None  # static | waiting | moving | holding | returning | done
    frame: Literal["ENU", "UNKNOWN"] = "ENU"


class Readiness(BaseModel):
    """Status details shown when a unit is inspected. Values are synthetic scenario state."""
    score: float = Field(ge=0, le=1, description="0..1 composite readiness computed by rules")
    fuelPct: float | None = None
    ammunitionPct: float | None = None
    crewPresent: int | None = None
    crewRequired: int | None = None
    commsStatus: Literal["nominal", "degraded", "lost", "n/a"] = "nominal"
    maintenanceDueH: float | None = None
    faults: list[str] = []
    notes: list[str] = []  # rule-derived context (weather, dependencies)
    lastReportAt: str | None = None


class Track(BaseModel):
    """Movement plan for a mobile entity: a sequence of waypoints with a cruise speed and a schedule."""
    waypoints: list[list[float]]  # [[lng, lat, altM?], ...]
    speedMps: float
    startAtS: float  # scenario seconds when movement begins
    loop: bool = False
    holdS: float = 0  # loiter at the end before looping/stopping


class SceneEntity(BaseModel):
    id: str
    resourceId: str
    kind: EntityKind
    domain: Domain
    affiliation: Affiliation = "own"
    label: str
    unit: str | None = None  # parent formation / operator
    modelKey: str | None = None
    region: str | None = None  # SCB county code of home region
    position: GeoPosition | None = None
    kinematics: Kinematics | None = None
    condition: Condition = "normal"
    readiness: Readiness | None = None
    capabilities: list[str] = []
    sourceKind: SourceKind = "simulated"
    sourceId: str | None = None
    observedAt: str | None = None
    stale: bool = False
    visualPriority: int = 0
    scenarioId: str = "sweden-synthetic"
    worldRevision: int = 1
    modelVersion: str = "1.0.0"
    track: Track | None = None  # legacy declared movement plan (planned provenance)
    sidc: str | None = None  # APP-6 / MIL-STD-2525C symbol identification code
    echelon: str | None = None
    parentId: str | None = None
    layer: str | None = None  # dot-separated layer id, e.g. "land.manoeuvre"
    platform: str | None = None  # public platform class
    siteId: str | None = None
    short: str | None = None
    rangeKm: float | None = None
    tags: list[str] = []


class InputReport(BaseModel):
    id: str
    channel: Channel
    authorLevel: AuthorLevel
    author: str
    receivedAt: str
    effectiveAt: str
    severity: Severity = "info"
    title: str
    text: str
    position: GeoPosition | None = None
    radiusM: float | None = None
    entityRefs: list[str] = []
    region: str | None = None
    tags: list[str] = []
    sourceKind: SourceKind = "simulated"
    acknowledged: bool = False


class InputIn(BaseModel):
    """Posted report. Bounded: every accepted input is persisted to the mutation log and replayed."""
    channel: Channel
    authorLevel: AuthorLevel
    author: str = Field(max_length=120)
    title: str = Field(max_length=300)
    text: str = Field(max_length=8_000)
    severity: Severity | None = None
    position: GeoPosition | None = None
    radiusM: float | None = Field(default=None, ge=0, le=2_000_000, allow_inf_nan=False)
    entityRefs: list[Annotated[str, Field(max_length=128)]] = Field(default=[], max_length=100)
    region: str | None = Field(default=None, max_length=64)
    tags: list[Annotated[str, Field(max_length=64)]] = Field(default=[], max_length=50)


class AttentionCell(BaseModel):
    key: str
    center: list[float]
    ring: list[list[float]]
    score: float
    peak: float
    reasons: list[str]
    contributors: list[str]


class Alert(BaseModel):
    id: str
    severity: Severity
    title: str
    detail: str
    createdAt: str
    ruleId: str
    inputIds: list[str] = []
    entityIds: list[str] = []
    layerIds: list[str] = []
    position: list[float] | None = None
    recommendedInterventionId: str | None = None
    acknowledged: bool = False


class OutcomeBand(BaseModel):
    label: Literal["best", "expected", "worst"]
    probability: float
    timeToEffectMin: float
    description: str


class InterventionOption(BaseModel):
    id: str
    title: str
    rationale: str
    steps: list[str]
    assignedEntityIds: list[str]
    etaMin: float | None
    successLikelihood: float
    riskLevel: Literal["low", "medium", "high"]
    resourceCost: dict[str, float]
    outcomes: list[OutcomeBand]
    ruleIds: list[str]
    distanceKm: float | None = None


class Intervention(BaseModel):
    id: str
    alertId: str
    title: str
    objective: str
    position: list[float] | None
    options: list[InterventionOption]
    recommendedOptionId: str
    status: Literal["proposed", "committed", "in_progress", "completed", "aborted"] = "proposed"
    committedOptionId: str | None = None
    committedAt: str | None = None
    progress: float = 0
    monitorAlerts: list[str] = []


class PredictedPath(BaseModel):
    entityId: str
    sourceKind: Literal["predicted"] = "predicted"
    method: str
    horizonS: float
    points: list[list[float]]  # [[lng, lat, tS], ...]
    uncertaintyRing: list[list[float]] | None = None
    threatenedEntityIds: list[str] = []
    etaS: float | None = None
    hypothesis: str = "constant velocity"
    probability: float = 1.0
    basedOn: list[str] = []


class LayerDef(BaseModel):
    id: str
    label: str
    group: str
    description: str
    minZoom: float = 0
    maxZoom: float = 24
    supports3d: bool = False
    sourceKinds: list[SourceKind] = []
    legend: list[dict[str, str]] = []


class ModeDef(BaseModel):
    id: str
    label: str
    description: str
    layers: list[str]
    camera: dict[str, float]
    kpis: list[str]


class RoleDef(BaseModel):
    id: str
    label: str
    scope: Literal["national", "regional", "functional"]
    description: str
    modes: list[ModeDef]
    defaultModeId: str


class EventIn(BaseModel):
    assetId: str
    kind: Literal["fault", "repair", "resupply", "comms_loss", "comms_restored"]
    expectedRevision: int = Field(ge=1)


class CommitIn(BaseModel):
    optionId: str
    expectedRevision: int = Field(ge=1)
