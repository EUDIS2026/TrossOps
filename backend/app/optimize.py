"""Strategy optimisation: assign one option per open intervention so that no unit is double-booked and the
weighted objective (severity-weighted time-to-effect minus success) is minimal. Exact Hungarian solve for the
small problems a national picture produces (tens of interventions), with named alternatives for comparison."""
from __future__ import annotations

from .inputs import SEVERITY_RANK
from .models import Alert, Intervention

BIG = 1e6


def hungarian(cost: list[list[float]]) -> list[int]:
    """Minimum-cost assignment for an n×m matrix (n ≤ m). Returns column index per row."""
    n, m = len(cost), len(cost[0])
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)
    way = [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    ans = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            ans[p[j] - 1] = j - 1
    return ans


def option_cost(iv: Intervention, opt, severity: str) -> float:
    w = 1 + SEVERITY_RANK[severity]
    eta = opt.etaMin if opt.etaMin is not None else 120
    return w * (eta / 60) * (1.5 - opt.successLikelihood) + (3 if opt.riskLevel == "high" else 1 if opt.riskLevel == "medium" else 0)


def optimise(interventions: list[Intervention], alerts: dict[str, Alert]) -> dict:
    """Return the optimal plan plus 'nearest' and 'highest-success' alternatives with their objective values."""
    open_ivs = [iv for iv in interventions if iv.status == "proposed" and iv.options]
    if not open_ivs:
        return {"status": "nothing_to_optimise", "plan": [], "alternatives": [], "method": "hungarian"}
    # Columns: (interventionIndex, optionIndex) pairs are not a plain assignment; expand units as columns.
    units: list[str] = sorted({eid for iv in open_ivs for o in iv.options for eid in o.assignedEntityIds} | {"__external__"})
    cols = units + [f"__slack_{k}" for k in range(len(open_ivs))]
    cost = []
    choice: list[dict[int, str]] = []
    for iv in open_ivs:
        sev = alerts[iv.alertId].severity if iv.alertId in alerts else "warning"
        row = [BIG] * len(cols)
        ch: dict[int, str] = {}
        for o in iv.options:
            key = o.assignedEntityIds[0] if o.assignedEntityIds else "__external__"
            j = cols.index(key)
            c = option_cost(iv, o, sev)
            if c < row[j]:
                row[j], ch[j] = c, o.id
        for k in range(len(open_ivs)):
            row[len(units) + k] = 50 * (1 + SEVERITY_RANK[sev])  # leaving it unassigned is costly but feasible
        cost.append(row)
        choice.append(ch)
    assign = hungarian(cost)
    plan, total = [], 0.0
    for i, iv in enumerate(open_ivs):
        j = assign[i]
        opt_id = choice[i].get(j)
        total += cost[i][j]
        plan.append({"interventionId": iv.id, "optionId": opt_id, "unit": cols[j] if j < len(units) and opt_id else None, "cost": round(cost[i][j], 2), "unassigned": opt_id is None})

    def alt(name: str, pick) -> dict:
        used: set[str] = set()
        items, obj = [], 0.0
        for iv in open_ivs:
            sev = alerts[iv.alertId].severity if iv.alertId in alerts else "warning"
            avail = [o for o in iv.options if not o.assignedEntityIds or o.assignedEntityIds[0] not in used]
            if not avail:
                items.append({"interventionId": iv.id, "optionId": None, "unit": None, "cost": 50 * (1 + SEVERITY_RANK[sev]), "unassigned": True})
                obj += 50 * (1 + SEVERITY_RANK[sev])
                continue
            o = pick(avail)
            if o.assignedEntityIds:
                used.add(o.assignedEntityIds[0])
            c = option_cost(iv, o, sev)
            obj += c
            items.append({"interventionId": iv.id, "optionId": o.id, "unit": o.assignedEntityIds[0] if o.assignedEntityIds else "__external__", "cost": round(c, 2), "unassigned": False})
        return {"name": name, "objective": round(obj, 2), "plan": items}

    alternatives = [alt("nearest-first", lambda opts: min(opts, key=lambda o: o.etaMin if o.etaMin is not None else 1e9)),
                    alt("highest-success", lambda opts: max(opts, key=lambda o: o.successLikelihood))]
    return {"status": "working", "method": "hungarian", "objective": round(total, 2), "plan": plan, "alternatives": alternatives,
            "explanation": "Objective per intervention = (1 + severity rank) × ETA[h] × (1.5 − success) + risk penalty; one unit per intervention; unassigned slack costs 50 × (1 + severity rank)."}
