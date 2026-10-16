// Mirrors backend/app/models.py field for field. Keep both in sync; the API is the authority.

export type SourceKind = 'observed' | 'simulated' | 'inferred' | 'predicted' | 'planned' | 'public' | 'unknown'
export type AltitudeDatum = 'WGS84_ELLIPSOID' | 'MSL' | 'AGL' | 'UNKNOWN'
export type EntityKind = 'fixed_wing' | 'helicopter' | 'multirotor' | 'ground_vehicle' | 'vessel' | 'personnel' | 'facility' | 'infrastructure' | 'unknown'
export type Domain = 'air' | 'land' | 'sea' | 'site' | 'infra' | 'unknown'
export type Affiliation = 'own' | 'allied' | 'civil' | 'unknown' | 'hostile_suspected'
export type Condition = 'normal' | 'degraded' | 'unavailable' | 'unknown'
export type Severity = 'info' | 'advisory' | 'warning' | 'critical'

export interface GeoPosition { longitudeDeg: number; latitudeDeg: number; altitudeM: number | null; altitudeDatum: AltitudeDatum; horizontalAccuracyM: number | null }
export interface Kinematics { headingDeg: number | null; speedMps: number | null; frame: 'ENU' | 'UNKNOWN' }
export interface Readiness {
  score: number; fuelPct: number | null; ammunitionPct: number | null; crewPresent: number | null; crewRequired: number | null
  commsStatus: 'nominal' | 'degraded' | 'lost' | 'n/a'; maintenanceDueH: number | null; faults: string[]; notes: string[]; lastReportAt: string | null
}
export interface Track { waypoints: number[][]; speedMps: number; startAtS: number; loop: boolean; holdS: number }
export interface SceneEntity {
  id: string; resourceId: string; kind: EntityKind; domain: Domain; affiliation: Affiliation; label: string; unit: string | null; modelKey: string | null
  region: string | null; position: GeoPosition | null; kinematics: Kinematics | null; condition: Condition; readiness: Readiness | null; capabilities: string[]
  sourceKind: SourceKind; sourceId: string | null; observedAt: string | null; stale: boolean; visualPriority: number; scenarioId: string; worldRevision: number
  modelVersion: string; track: Track | null
}
export type Channel = 'field_report' | 'unit_sitrep' | 'logistics_report' | 'maintenance_log' | 'sensor_detection' | 'intel_report' | 'civil_emergency' | 'weather_advisory'
  | 'infrastructure_status' | 'public_news' | 'cyber_alert' | 'command_directive' | 'allied_liaison' | 'head_of_state_directive'
export interface InputReport {
  id: string; channel: Channel; authorLevel: string; author: string; receivedAt: string; effectiveAt: string; severity: Severity; title: string; text: string
  position: GeoPosition | null; radiusM: number | null; entityRefs: string[]; region: string | null; tags: string[]; sourceKind: SourceKind; acknowledged: boolean
}
export interface AttentionCell { key: string; center: number[]; ring: number[][]; score: number; peak: number; reasons: string[]; contributors: string[] }
export interface AttentionResponse { atS: number; worldRevision: number; resolution: string; cellDeg: number; unit: string; maxScore: number; cells: AttentionCell[]
  contributions: { lng: number; lat: number; radiusM: number; weight: number; reason: string; contributor: string; ruleId: string }[] }
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
export interface PredictedPath { entityId: string; sourceKind: 'predicted'; method: string; horizonS: number; points: number[][]; uncertaintyRing: number[][] | null; threatenedEntityIds: string[]; etaS: number | null }
export interface Area { id: string; label: string; kind: 'operational_area' | 'restricted_zone' | 'coverage_model'; ring: number[][]; requires: string[]; priority: number; status: string; blockers: string[] }
export interface WorldEvent { id: string; assetId: string; kind: string; worldRevision: number; recordedAt: string; atS: number; sourceKind: string }
export interface LayerDef { id: string; label: string; group: string; description: string; minZoom: number; maxZoom: number; supports3d: boolean; sourceKinds: SourceKind[]; legend: Record<string, string>[] }
export interface ModeDef { id: string; label: string; description: string; layers: string[]; camera: { lng: number; lat: number; zoom: number; pitch: number; bearing: number }; kpis: string[] }
export interface RoleDef { id: string; label: string; scope: 'national' | 'regional' | 'functional'; description: string; modes: ModeDef[]; defaultModeId: string }
export interface Views { roles: RoleDef[]; layers: LayerDef[]; rules: { id: string; title: string }[]; channels: { id: Channel; label: string; level: string; weight: number }[]; regionScope: Record<string, string[]> }
export interface LayerAttention { count: number; severity: Severity; alertIds: string[] }
export interface Snapshot {
  scenarioId: string; worldRevision: number; modelVersion: string; atS: number; atTime: string; serverNow: string; nowS: number; speed: number; live: boolean
  sourceKind: SourceKind; dataNotice: string; role: string | null; entities: SceneEntity[]; areas: Area[]; alerts: Alert[]; interventions: Intervention[]
  predictions: PredictedPath[]; inputs: InputReport[]; events: WorldEvent[]; kpis: Record<string, number | string | null>; layerAttention: Record<string, LayerAttention>
  ruleTrace: Record<string, unknown>[]; priorities: Record<string, number>
}
export interface KinematicsTick { atS: number; atTime: string; worldRevision: number; rows: [string, number, number, number | null, number | null, number | null, Condition][] }
export interface EntityDetail { entity: SceneEntity; inputs: InputReport[]; alerts: Alert[]; interventions: Intervention[]; predictions: PredictedPath[]; areas: string[]; events: WorldEvent[]; worldRevision: number; atS: number; ruleTrace: Record<string, unknown>[] }
export interface TrackResponse { entityId: string; sourceKind: SourceKind; fromS: number; toS: number; stepS: number; samples: (number | null)[][]; note: string }
export interface PlanResult { status: string; method: string; objective?: number; plan: { interventionId: string; optionId: string | null; unit: string | null; cost: number; unassigned: boolean }[]
  alternatives: { name: string; objective: number; plan: PlanResult['plan'] }[]; explanation?: string; worldRevision: number; atS: number }
export interface Forecast { status: 'connected' | 'unavailable'; source: string; location: string; label: string; sourceUrl?: string; requestedPoint?: number[]; gridPoint?: number[]
  referenceTime?: string; validTime?: string; reason?: string; data?: Record<string, number | null>; units?: Record<string, string> }
export interface Clock { epoch: string; nowS: number; serverNow: string; speed: number; worldRevision: number }
