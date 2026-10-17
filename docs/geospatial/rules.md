# Rule engine

Deterministic, traceable, no learned model. Each rule reads the world at scenario time `t` and the inputs effective by then, and writes attention contributions, alerts, interventions, predictions and derived statuses. Every output names its rule and the input ids it was derived from; `/api/entities/{id}` returns the trace for one entity.

| Rule | Fires on | Produces |
|---|---|---|
| R01 Unknown track approach | any `unknown` affiliation entity | 30 min dead-reckoned path with uncertainty wedge, closest approach to own sites, attention along the path, alert (critical < 25 km, warning otherwise, advisory once J2 downgrades), intervention "identify" with air/sea candidates ranked by success and intercept time |
| R02 Readiness thresholds | own unit with fuel < 25 % (aircraft < 12 %) or readiness < 0.45 | attention; advisory, warning below 15 % fuel (aircraft 8 %) or readiness 0.30; resupply intervention from the nearest fuel/supply source (ground and sea units) |
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
| R16 Small UAS near sites | small UAS tracks within 6 km of an own or civil site, drone reports about a site | critical with ≥ 2 tracks or a track plus a second channel, warning with a track or ≥ 2 channels, advisory for one report; counter-UAS and ground-search options (not for advisory) |
| R17 Maritime anomaly over undersea infrastructure | unknown sea track < 3 km from a cable or pipeline, slow (< ~3 kn) or AIS-dark | critical when slow and dark, advisory when a weather advisory explains the low speed, warning otherwise; shadow-and-hail options |
| R18 GNSS interference | inputs tagged `gnss`/`spoofing` with a position | own and civil air/sea platforms inside −0.08 readiness (not stacked), alert |
| R19 Pattern indicators on real traffic | real AIS loitering over a cable corridor, real ADS-B orbit patterns | neutral indicator alert; observation options for vessels |
| R20 Emergency squawks | real ADS-B 7500/7600/7700 | alert at the report's severity, corroborated by a 112 report within 50 km; SAR stand-by options except for 7600 |
| R21 Real road situations | `road_situation` (Trafikverket) within 500 m of the route ahead of a moving own column (tail to 80 km beyond its lead); accidents/obstructions within 5 km of an own site | per column: warning for accidents and obstructions (re-route and hold options), advisory for restrictions (warning at Trafikverket impact 4–5), info for traffic information or a situation expected to clear before the lead arrives; ignored if it starts after the tail has passed. Near sites: info context (advisory at impact 4–5) |
| R22 Real thermal anomalies | `thermal_anomaly` (NASA FIRMS VIIRS) within 3 km of an own site (warning, verify options), within 10 km of an own site or 2 km of a column's route ahead (advisory) | heat seen on day and night passes is persistent (industry, flares) and drops one step; every alert states that VIIRS detects heat, not fire |

## Real feeds as inputs

`feed_inputs.py` turns cached public feed payloads into inputs; an evaluation never waits on the network, and a malformed item never breaks it (per-item guards, and the engine drops all external inputs if the translation raises).

- **Trafikverket road situations → `road_situation`** (graded A2). Accidents (Olycka), obstructions (Hinder), restrictions (Restriktion) and important traffic information with a position, in force now or starting within 6 h, not ended; an accident with no end time older than 12 h is dropped as stale. Severity: accidents and obstructions advisory, the rest info, one step higher at Trafikverket impact 4–5. The end time travels as a `valid_to:` tag.
- **NASA FIRMS → `thermal_anomaly`** (graded B3: a reliable detection of heat, an uncertain cause). VIIRS detections from the last 24 h with nominal or high confidence, clustered within 1.5 km into one input per heat source; the id is the earliest detection, so it stays stable as later passes add detections. Advisory at ≥ 10 MW peak FRP, info below. Tagged `persistent` when seen on both day and night passes.
- **Relevance** (`relevance.py`). Hundreds of nationwide roadworks or fire pixels would bury the operational reports, so the engine keeps a road situation only within 2 km of an own road-march route or 5 km of an own site, and a thermal anomaly within 3 km of a route, 15 km of an own site, or 25 km of a report tagged `explosion` or `fire`.
- **Columns** (`engine.columns_at`). Own land units on a declared or planned path of at least 20 km that are moving form one column per route and direction; the rules see the route from the column's tail to 80 km beyond its lead, with the column's length and mean speed (for the time to reach a situation).

## Thermal corroboration of explosion and fire reports

Public news, field reports and police events tagged `explosion` or `fire` (operator text: "explosion", "blast", "detonat…", "fire", "burning", "flames"; negated mentions such as "no fire" and "fired", "firewall", "firearm" do not count) are checked against FIRMS in the deception assessment:

- **N6 Thermal anomaly corroborates (−1.0):** a heat source within 5 km of the report (widened to the report's own radius, at most 25 km) that first appeared between 1 h before and 12 h after the report. A source already burning earlier is pre-existing heat (industry) and does not count.
- **D15 No thermal anomaly after a satellite pass (+0.4):** nothing qualifying, although the feed holds a VIIRS acquisition at least 30 min after the report (evidence of a later overpass) and the report is less than 24 h old. Weak by design: cloud, small or brief events and 375 m pixels hide many real explosions. With FIRMS unavailable neither indicator fires.

## Options and outcomes

`success = clamp(base + 0.35 × (readiness − 0.6) − weatherPenalty − latePenalty)`, where `latePenalty` grows with ETA beyond the rule's deadline. Outcome bands: best = 0.45 × success at 0.9 × ETA, expected = 0.55 × success at 1.15 × ETA, worst = 1 − success at 1.6 × ETA. These are declared synthetic planning figures, shown with their formula in the UI.

## Optimiser

`POST /api/strategy/optimize` solves one option per open intervention with no unit double-booked (Hungarian assignment). Objective per intervention = (1 + severity rank) × ETA[h] × (1.5 − success) + risk penalty; leaving an intervention unassigned costs 50 × (1 + severity rank). Two named alternatives (nearest-first, highest-success) are returned with their objective for comparison.

## Attention

Contribution = (point, radius, weight, reason, contributor, rule). Cell score = Σ weight × (1 − d/r)^1.5 over contributions reaching the cell; the API returns cells with their top three reasons and contributors, and the raw contributions for the heatmap. The unit is "attention weight"; the legend states this and the peak value.
