# Rule engine

Deterministic, traceable, no learned model. 19 rules (R01–R20; there is no R09), listed by `GET /api/views` → `rules`. Each rule reads the world at scenario time `t` and the inputs effective by then, and writes attention contributions, alerts, interventions, predictions and derived statuses. Every output names its rule and the input ids it was derived from; `/api/entities/{id}` returns the trace for one entity.

| Rule | Fires on | Produces |
|---|---|---|
| R01 Unknown track approach | any `unknown` affiliation entity | 30 min dead-reckoned path with uncertainty wedge, closest approach to own sites, attention along the path, alert (critical < 25 km, warning otherwise, advisory once J2 downgrades), intervention "identify" with air/sea candidates ranked by success and intercept time |
| R02 Readiness thresholds | own unit with fuel < 30 % or readiness < 0.5 | attention, advisory/warning, resupply intervention from the nearest fuel/supply source |
| R03 Reported faults | maintenance/field/unit reports tagged `fault` | entity degraded, warning, recovery intervention |
| R04 Communications | reports tagged `comms`/`cyber`, or comms status degraded/lost | comms hubs degraded, warning/critical, relay intervention |
| R05 Infrastructure outage | `infrastructure_status` ≥ advisory | node degraded, dependents −0.15 readiness with a note, attention over the outage radius, generator intervention for power outages |
| R06 Civil emergency | `civil_emergency` with a position | attention, alert at report severity, medevac (air) and medical team (land) options |
| R07 Weather advisory | `weather_advisory` with a position | advisory, air/sea units inside the area −0.1 readiness, weather penalty applied to every air option's success |
| R08 Intelligence | `intel_report` ≥ advisory | area priority ×1.3, attention, alert |
| R10 Area coverage | operational areas | covered / degraded / uncovered from required entities' condition and readiness, alert when blocked, priority-weighted attention |
| R11 Directives | `command_directive` (×1.5) and `head_of_state_directive` (×2.0) | area priority multipliers, attention on referenced entities, alert |
| R12 Stale reporting | comms lost | entity marked stale (faded icon, frozen motion) |
| R13 Mid-intervention monitoring | committed interventions | progress from committed time and ETA; re-plan alert when the assigned unit degrades, runs low on fuel or weather now covers the objective |
| R14 Open-source reporting | `public_news` with a position | low attention, info alert with OPSEC note |
| R15 Allied offers | `allied_liaison` tagged `offer` | adds an allied option to unknown-track interventions |
| R16 Small UAS near protected sites | unknown tracks tagged `small_uas` near an own or civil site, or reports tagged `drone` / `small_uas` about a site (by reference, or by position for police and public reports) | attention; severity by independent corroboration (one report advisory, tracks or two channels warning, ≥ 2 tracks or tracks confirmed by a second channel critical); counter-UAS and ground-search options |
| R17 Maritime anomaly over undersea infrastructure | unknown or suspect vessel within 3 km of a cable or pipeline that is slow (< 1.6 m/s) or AIS-dark | attention, warning (critical when dark and slow), protect-and-identify intervention |
| R18 GNSS interference | inputs tagged `gnss` / `spoofing` with a position (injected, or real ADS-B integrity clusters) | own and civil air/sea platforms inside the radius −0.08 readiness with a note, attention, alert |
| R20 Emergency squawks on real air traffic | real ADS-B inputs tagged `squawk` (7500 / 7600 / 7700) | attention, alert at the report's severity, corroborated by a 112 report within 50 km; search-and-rescue options for 7700 and 7500; describes the squawk, not intent |
| R19 Pattern indicators on real traffic | real-feed inputs tagged `cable` (AIS vessel slow over a cable corridor ≥ 20 min) or `orbit` (ADS-B orbit / racetrack) | attention, alert, observation intervention; wording stays neutral (indicator, not an assessment of the named traffic) |

## Real feeds as inputs

`feed_inputs.py` turns cached public payloads into inputs (never waiting on the network): SMHI warnings (yellow and
above) → `weather_advisory` (R07); police events with drone, sabotage, explosion or shooting keywords in the last 6 h →
`police_event` (R16 by position near an own site, and deception indicators); emergency squawks 7500/7600/7700 →
`sensor_detection` tagged `squawk` (R20); clusters of ≥ 3 aircraft with degraded GNSS integrity →
`sensor_detection` tagged `gnss` (R18); AIS cable loitering and ADS-B orbits → R19 indicators. They carry
`sourceKind` `public` or `observed` and are evaluated only for the present.

## Options and outcomes

`success = clamp(base + 0.35 × (readiness − 0.6) − weatherPenalty − latePenalty)`, where `latePenalty` grows with ETA beyond the rule's deadline. Outcome bands: best = 0.45 × success at 0.9 × ETA, expected = 0.55 × success at 1.15 × ETA, worst = 1 − success at 1.6 × ETA. These are declared synthetic planning figures, shown with their formula in the UI.

## Optimiser

`POST /api/strategy/optimize` solves one option per open intervention with no unit double-booked (Hungarian assignment). Objective per intervention = (1 + severity rank) × ETA[h] × (1.5 − success) + risk penalty; leaving an intervention unassigned costs 50 × (1 + severity rank). Two named alternatives (nearest-first, highest-success) are returned with their objective for comparison.

## Attention

Contribution = (point, radius, weight, reason, contributor, rule). Cell score = Σ weight × (1 − d/r)^1.5 over contributions reaching the cell; the API returns cells with their top three reasons and contributors, and the raw contributions for the heatmap. The unit is "attention weight"; the legend states this and the peak value.
