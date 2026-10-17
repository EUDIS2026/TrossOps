// Mirrors backend/app/models.py and the engine payloads. Keep both in sync; the API is the authority.
import type { MotionApi, Vertex } from '../core/motion'

export type SourceKind = 'observed' | 'simulated' | 'inferred' | 'predicted' | 'planned' | 'public' | 'unknown'
export type AltitudeDatum = 'WGS84_ELLIPSOID' | 'MSL' | 'AGL' | 'UNKNOWN'
export type EntityKind = 'fixed_wing' | 'helicopter' | 'multirotor' | 'ground_vehicle' | 'vessel' | 'personnel' | 'facility' | 'infrastructure' | 'unknown' | 'formation'
export type Domain = 'air' | 'land' | 'sea' | 'site' | 'infra' | 'unknown'
export type Affiliation = 'own' | 'allied' | 'civil' | 'unknown' | 'hostile_suspected'
export type Condition = 'normal' | 'degraded' | 'unavailable' | 'unknown'
export type Severity = 'info' | 'advisory' | 'warning' | 'critical'

export interface GeoPosition { longitudeDeg: number; latitudeDeg: number; altitudeM: number | null; altitudeDatum: AltitudeDatum; horizontalAccuracyM: number | null }
export interface Kinematics { headingDeg: number | null; speedMps: number | null; pitchDeg: number; bankDeg: number; phase: string | null; frame: 'ENU' | 'UNKNOWN' }
export interface Readiness {
  score: number; fuelPct: number | null; ammunitionPct: number | null; crewPresent: number | null; crewRequired: number | null
  commsStatus: 'nominal' | 'degraded' | 'lost' | 'n/a'; maintenanceDueH: number | null; faults: string[]; notes: string[]; lastReportAt: string | null
}
export interface SceneEntity {
  id: string; resourceId: string; kind: EntityKind; domain: Domain; affiliation: Affiliation; label: string; unit: string | null; modelKey: string | null
  region: string | null; position: GeoPosition | null; kinematics: Kinematics | null; condition: Condition; readiness: Readiness | null; capabilities: string[]
  sourceKind: SourceKind; sourceId: string | null; observedAt: string | null; stale: boolean; visualPriority: number; worldRevision: number
  sidc: string | null; echelon: string | null; parentId: string | null; layer: string | null; platform: string | null; siteId: string | null; short: string | null
  rangeKm: number | null; tags: string[]
}

/** Order-of-battle entry from /api/world. Formations have no motion; their position is derived from their platforms. */
export interface CatalogEntity {
  id: string; label: string; short: string | null; kind: EntityKind; domain: Domain; affiliation: Affiliation; sidc: string | null; echelon: string | null
  parentId: string | null; layer: string | null; platform: string | null; model: string | null; siteId: string | null; region: string | null
  capabilities: string[]; rangeKm: number | null; tags: string[]; unit: string | null; sourceKind: SourceKind; motion?: MotionApi | null
}
export interface SiteSummary { id: string; kind: string; center: [number, number]; axis: number; footprint: number[][]; runway: { start: number[]; end: number[]; heading: number; lengthM: number } | null }
export interface Area { id: string; label: string; kind: 'operational_area' | 'restricted_zone' | 'coverage_model'; ring: number[][]; requires: string[]; priority: number; status?: string; blockers?: string[]; priorityBasis?: string[] }
export interface Cable { id: string; label: string; kind: string; coords: number[][] }
export interface PlanRecord { entityId: string; path: Vertex[]; speeds: number[]; startS: number; label: string; worldRevision: number; recordedAt: string }
export interface WorldCatalog {
  scenarioId: string; modelVersion: string; catalogRevision: number; worldRevision: number; epoch: string; speed: number; dataNotice: string
  entities: CatalogEntity[]; routes: Record<string, { path: Vertex[]; speeds: number[] }>; sites: SiteSummary[]; areas: Area[]; cables: Cable[]; plans: PlanRecord[]
}

export type Channel = 'field_report' | 'unit_sitrep' | 'logistics_report' | 'maintenance_log' | 'sensor_detection' | 'intel_report' | 'civil_emergency' | 'weather_advisory'
  | 'infrastructure_status' | 'public_news' | 'cyber_alert' | 'command_directive' | 'allied_liaison' | 'head_of_state_directive' | 'police_event' | 'crisis_info'
  | 'road_situation' | 'thermal_anomaly'
export interface InputReport {
  id: string; channel: Channel; authorLevel: string; author: string; receivedAt: string; effectiveAt: string; severity: Severity; title: string; text: string
  position: GeoPosition | null; radiusM: number | null; entityRefs: string[]; region: string | null; tags: string[]; sourceKind: SourceKind; acknowledged: boolean
}
export interface AttentionContribution { lng: number; lat: number; radiusM: number; weight: number; reason: string; contributor: string; ruleId: string }
export interface AttentionResponse { atS: number; worldRevision: number; resolution: string; cellDeg: number; unit: string; maxScore: number; cells: { key: string; center: number[]; ring: number[][]; score: number; peak: number; reasons: string[]; contributors: string[] }[]
  contributions: AttentionContribution[] }
export interface Alert {
  id: string; severity: Severity; title: string; detail: string; createdAt: string; ruleId: string; inputIds: string[]; entityIds: string[]; layerIds: string[]
  position: number[] | null; recommendedInterventionId: string | null; acknowledged: boolean
}
export interface OutcomeBand { label: 'best' | 'expected' | 'worst'; probability: number; timeToEffectMin: number; description: string }
export interface InterventionOption {
  id: string; title: string; rationale: string; steps: string[]; assignedEntityIds: string[]; etaMin: number | null; successLikelihood: number
  riskLevel: 'low' | 'medium' | 'high'; resourceCost: Record<string, number>; outcomes: OutcomeBand[]; ruleIds: string[]; distanceKm: number | null
}
export interface Intervention {
  id: string; alertId: string; title: string; objective: string; position: number[] | null; options: InterventionOption[]; recommendedOptionId: string
  status: 'proposed' | 'committed' | 'in_progress' | 'completed' | 'aborted'; committedOptionId: string | null; committedAt: string | null; progress: number; monitorAlerts: string[]
}
export interface PredictedPath {
  entityId: string; sourceKind: 'predicted'; method: string; horizonS: number; points: number[][]; uncertaintyRing: number[][] | null
  threatenedEntityIds: string[]; etaS: number | null; hypothesis: string; probability: number; basedOn: string[]
}
export interface Indicator { id: string; label: string; weight: number; evidence: string; rawWeight?: number; group?: string }
export interface Deception { subject: string; kind: 'track' | 'report'; hypothesis: string; prior: number; logOdds: number; probability: number; band: string; indicators: Indicator[]; wouldChange: string[]; method: string }
export interface FusionSource { inputId: string | null; channel: string; channelLabel: string; author: string; at: string; grading: string; reliability: string; credibility: string; confidence: number; title: string; sourceKind: SourceKind; independence?: string; gradingBasis?: string }
export interface Fusion { subject: string; sources: FusionSource[]; channels: string[]; corroboration: number; independentSources?: string[]; confidence: number; method: string; identity?: { hypothesis: string; probability: number; indicators: string[] }[] }
export interface WorldEvent { id: string; assetId: string; kind: string; worldRevision: number; recordedAt: string; atS: number; sourceKind: string }
export interface LayerDef { id: string; label: string; group: string; description: string; minZoom: number; maxZoom: number; supports3d: boolean; sourceKinds: SourceKind[]; legend: Record<string, string>[] }
export interface ModeDef { id: string; label: string; description: string; layers: string[]; camera: { lng: number; lat: number; zoom: number; pitch: number; bearing: number }; kpis: string[] }
export interface RoleDef { id: string; label: string; scope: 'national' | 'regional' | 'functional'; description: string; modes: ModeDef[]; defaultModeId: string }
export interface Views { roles: RoleDef[]; layers: LayerDef[]; rules: { id: string; title: string }[]; channels: { id: Channel; label: string; level: string; weight: number }[]; regionScope: Record<string, string[]>; exclusiveGroups: string[] }
export interface LayerAttention { count: number; severity: Severity; alertIds: string[] }
export type StatusRow = [Condition, number | null, number | null, number | null, string | null, boolean, number]
export type ObservedRow = [string, number, number, number | null, number | null, number | null, Condition]
export interface Snapshot {
  scenarioId: string; worldRevision: number; catalogRevision: number; modelVersion: string; atS: number; atTime: string; serverNow: string; nowS: number; speed: number
  live: boolean; future: boolean; sourceKind: SourceKind; dataNotice: string; role: string | null; status: Record<string, StatusRow>; scope: string[] | null
  observed: ObservedRow[]; areas: Area[]; alerts: Alert[]; interventions: Intervention[]; predictions: PredictedPath[]; inputs: InputReport[]; events: WorldEvent[]
  kpis: Record<string, number | string | null>; layerAttention: Record<string, LayerAttention>; ruleTrace: Record<string, unknown>[]; priorities: Record<string, number>
  deception: Record<string, Deception>; fusion: Record<string, Fusion>
}
export interface KinematicsTick { atS: number; atTime: string; worldRevision: number; catalogRevision: number; rows: ObservedRow[] }
export interface EntityDetail {
  entity: SceneEntity; inputs: InputReport[]; alerts: Alert[]; interventions: Intervention[]; predictions: PredictedPath[]; areas: string[]; events: WorldEvent[]
  worldRevision: number; atS: number; ruleTrace: Record<string, unknown>[]; fusion: Fusion | null; deception: Deception | null; plan: PlanRecord | null
  layout: SiteLayout | null; based: string[]
}
export interface FormationDetail {
  formation: SceneEntity; children: string[]; platforms: number; byPlatform: Record<string, number>; readiness: number | null; fuel: number | null
  unavailable: number; degraded: number; moving: number; alerts: Alert[]; worldRevision: number; atS: number
}
export interface SiteLayout {
  siteId: string; kind: string; center: number[]; axis: number; features: GeoJSON.FeatureCollection; spots: Record<string, { id: string; lng: number; lat: number; heading: number; kind: string }[]>
  runway: SiteSummary['runway']; footprint: number[][]
}
export interface TrackResponse { entityId: string; sourceKind: SourceKind; fromS: number; toS: number; stepS: number; samples: (number | null)[][]; note: string }
export interface PlanResult { status: string; method: string; objective?: number; plan: { interventionId: string; optionId: string | null; unit: string | null; cost: number; unassigned: boolean }[]
  alternatives: { name: string; objective: number; plan: PlanResult['plan'] }[]; explanation?: string; worldRevision: number; atS: number }
export interface RouteOption {
  id: string; label: string; path: Vertex[]; speeds: number[]; distanceKm: number; etaMin: number; fuelUsePct: number; fuelAfterPct: number | null
  exposureKm: number; exposure: string[]; risk: number; feasible: boolean; notes: string[]; basedOn: string[]; airborne: boolean; score: number
  terrain?: { groundM: (number | null)[]; distanceM?: number[]; minM: number | null; maxM: number | null; climbM?: number; minClearanceM?: number | null }
}
export interface RoutePlan { entityId: string; from: number[]; to: number[]; options: RouteOption[]; recommended: string; method: string; worldRevision: number; atS: number }
export interface Clock { epoch: string; nowS: number; serverNow: string; speed: number; worldRevision: number; catalogRevision: number }

// ---- real public feeds (/api/live, /api/env, /api/civil) ---------------------------------------------------------
export type FeedStatus = 'working' | 'partial' | 'simulated' | 'adapter-only' | 'planned' | 'blocked'
export interface SourceStatus { id: string; label: string; category: string; status: FeedStatus; lastOkAt: string | null; lastError: string | null; count: number | null; licence: string; url: string; note: string | null; stale: boolean }
export interface LiveAircraft { id: string; callsign: string | null; registration: string | null; type: string | null; category: string | null; lng: number; lat: number; altM: number | null; altDatum: string
  onGround?: boolean; speedMps: number | null; headingDeg: number | null; verticalRateMps: number | null; squawk: string | null; emergency: string | null; military: boolean; nic: number | null; nacp: number | null; seenS: number | null; source: string }
export interface LiveVessel { id: string | number; name: string | null; callsign: string | null; imo: number | null; shipType: number | null; shipTypeLabel: string | null; lng: number; lat: number
  speedMps: number | null; courseDeg: number | null; headingDeg: number | null; navStatus: number | null; navStatusLabel: string | null; destination: string | null; timestampMs: number | null; source: string }
// ---- terrain (/api/terrain, Lantmäteriet Markhöjd Direkt; 503 while not configured) -----------------------------
export interface TerrainElevation { lng: number; lat: number; groundM: number | null; datum: string; source: string }
export interface TerrainProfile { distanceM: number[]; groundM: (number | null)[]; points: [number, number][]; minM: number | null; maxM: number | null; climbM: number; source: string }
export interface LineOfSight {
  visible: boolean; minClearanceM: number | null; obstruction: { lng: number; lat: number; distanceM: number; groundM: number } | null
  distanceM: number; observerM: number; targetM: number; profile: TerrainProfile & { clearanceM: (number | null)[] }; method: string
}
export interface FeedPayload<T> { status: FeedStatus; source?: string; licence?: string; fetchedAt?: string; stale?: boolean; items?: T[]; [k: string]: unknown }
