/** Scenario clock on the client. Live follows the server clock; simulation runs at any rate from any point, into the
 * past (replay) or the future (planned motion and predictions only — real feeds are hidden there). Motion is evaluated
 * locally, so changing rate costs nothing; the evaluated picture (alerts, status) is fetched on a coarser grid. */

export type ClockMode = 'live' | 'sim'

export class SimClock {
  mode: ClockMode = 'live'
  rate = 1
  paused = false
  speed = 1 // server scenario seconds per wall second
  private serverAt = 0 // scenario seconds at `wallAt`
  private wallAt = 0
  private simAt = 0
  private simWall = 0

  /** Align live time with the server: nowS observed at the moment of the response. */
  sync(nowS: number, speed: number) {
    this.serverAt = nowS; this.wallAt = performance.now(); this.speed = speed || 1
  }

  liveNow(): number { return this.wallAt ? this.serverAt + ((performance.now() - this.wallAt) / 1000) * this.speed : 0 }

  now(): number {
    if (this.mode === 'live') return this.liveNow()
    if (this.paused) return this.simAt
    return this.simAt + ((performance.now() - this.simWall) / 1000) * this.rate * this.speed
  }

  goLive() { this.mode = 'live'; this.rate = 1; this.paused = false }
  jumpTo(t: number) { this.mode = 'sim'; this.simAt = Math.max(0, t); this.simWall = performance.now() }
  setRate(rate: number) { const t = this.now(); if (this.mode === 'live') this.mode = 'sim'; this.rate = rate; this.paused = false; this.jumpTo(t) }
  pause() { const t = this.now(); this.mode = 'sim'; this.paused = true; this.simAt = t }
  resume() { if (this.paused) { this.paused = false; this.simWall = performance.now() } }
  /** Seconds ahead of (positive) or behind (negative) live. */
  offset(): number { return this.now() - this.liveNow() }
}
