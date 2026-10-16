# TrossOps — product vision (owner's specification, October 2026)

A Sweden national-level platform that integrates every available input and outputs it on one sophisticated map.

## What it must do

- **Roles → modes → layers.** Every role (national commander down to a regional logistics officer) gets its own views; each view has mode-based maps; each map is composed of separable layers that can be shown in 2D or 3D.
- **Everything is clickable.** From a national overview down to a single GPS-localised vehicle, with readiness and status details, and everything around it in context.
- **Attention heat map.** A 3D "attention here" surface that can be switched off, computed by the rule engine from all inputs.
- **Layer switches with attention dots.** Each layer switch carries a red dot when that layer needs the operator's eyes — this is a live environment.
- **Zoom semantics.** 100 m shows different things than 1 km; the map auto-defines clusters of activity at every level and each cluster is clickable, down to the single unit at maximum zoom.
- **Inputs.** Public information plus at least ten text-based channels, from a soldier's personal report up to a head-of-state directive.
- **Rule engine, no AI in the demo.** Deterministic rules process absolutely all inputs into decisions, the heat map, intervention strategies, outcome possibilities, mid-intervention alerts and paths of action. AI can be added at several layers later; the demo must not depend on it.
- **Prediction and optimisation.** Trajectories, intercepts, time-to-effect and strategy optimisation, with technical depth that an engineer can trace.
- **Take the human factor out of every level of operation during use.** A national commander should see Sweden as one asset to be diagnosed.
- **Apple.com-level UX.** Sophistication, smoothness and a near-zero barrier to entry.
- **Latest tool versions**, integrated along a documented path.

## What it must not do

- Invent real military positions, identities or capabilities. All operational content is synthetic and labelled.
- Hide a mock behind a working-looking control.
