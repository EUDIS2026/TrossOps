# Rule engine

Deterministic, traceable, no learned model. Each rule reads the world at scenario time `t` and the inputs effective by then, and writes attention contributions, alerts, interventions, predictions and derived statuses. Every output names its rule and the input ids it was derived from; `/api/entities/{id}` returns the trace for one entity.

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

## Options and outcomes

`success = clamp(base + 0.35 × (readiness − 0.6) − weatherPenalty − latePenalty)`, where `latePenalty` grows with ETA beyond the rule's deadline. Outcome bands: best = 0.45 × success at 0.9 × ETA, expected = 0.55 × success at 1.15 × ETA, worst = 1 − success at 1.6 × ETA. These are declared synthetic planning figures, shown with their formula in the UI.

## Optimiser

`POST /api/strategy/optimize` solves one option per open intervention with no unit double-booked (Hungarian assignment). Objective per intervention = (1 + severity rank) × ETA[h] × (1.5 − success) + risk penalty; leaving an intervention unassigned costs 50 × (1 + severity rank). Two named alternatives (nearest-first, highest-success) are returned with their objective for comparison.

## Attention

Contribution = (point, radius, weight, reason, contributor, rule). Cell score = Σ weight × (1 − d/r)^1.5 over contributions reaching the cell; the API returns cells with their top three reasons and contributors, and the raw contributions for the heatmap. The unit is "attention weight"; the legend states this and the peak value.
