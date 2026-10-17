/** Cinematic camera intents. Every move is interruptible (drag, wheel, touch) and collapses to an instant jump when
 * the operator prefers reduced motion. A site selection arrives low and offset from the main axis, then orbits slowly
 * so the installation reads in depth until the operator takes the controls. */
import type { LngLatBounds, Map as MlMap } from 'maplibre-gl'

export class CinematicCamera {
  private orbitRaf = 0
  private orbitTimer = 0
  private stopTimer = 0
  private gen = 0 // bumped by every interrupt: callbacks queued by an older move must not resume it

  constructor(private map: MlMap) {}

  interrupt() {
    this.gen++
    cancelAnimationFrame(this.orbitRaf); window.clearTimeout(this.orbitTimer); window.clearTimeout(this.stopTimer)
    this.orbitRaf = 0
  }

  fly(cam: { lng: number; lat: number; zoom: number; pitch: number; bearing: number }, reduced: boolean) {
    this.interrupt()
    this.map.flyTo({ center: [cam.lng, cam.lat], zoom: cam.zoom, pitch: cam.pitch, bearing: cam.bearing, duration: reduced ? 0 : 2200, curve: 1.5, essential: true })
  }

  focusPoint(lng: number, lat: number, zoom: number, pitch: number, reduced: boolean, altM = 0) {
    this.interrupt()
    if (altM > 0) { this.map.setCenterClampedToGround(false); this.map.setCenterElevation(altM) }
    const far = this.map.getZoom() < zoom - 3
    this.map.flyTo({ center: [lng, lat], zoom, pitch, duration: reduced ? 0 : far ? 2600 : 1300, curve: far ? 1.7 : 1.2, speed: 0.9, essential: true })
  }

  focusBounds(b: LngLatBounds, pitch: number, reduced: boolean) {
    this.interrupt()
    const cam = this.map.cameraForBounds(b, { padding: { top: 140, bottom: 170, left: 120, right: 460 }, maxZoom: 15.5 })
    if (!cam) return
    this.map.flyTo({ ...cam, pitch, duration: reduced ? 0 : 1900, curve: 1.5, essential: true })
  }

  /** Approach a site: curved fly-in to a low, pitched view off the main axis, then a slow orbit. */
  cinematicSite(lng: number, lat: number, zoom: number, bearing: number, reduced: boolean) {
    this.interrupt()
    if (reduced) { this.map.jumpTo({ center: [lng, lat], zoom, pitch: 60, bearing }); return }
    const far = this.map.getZoom() < 9
    const gen = this.gen
    if (far) {
      // two-stage: a high establishing shot, then the descent onto the base
      this.map.flyTo({ center: [lng, lat], zoom: 11.2, pitch: 35, bearing: bearing - 40, duration: 2400, curve: 1.8, essential: true })
      this.map.once('moveend', () => {
        if (gen !== this.gen) return
        this.map.flyTo({ center: [lng, lat], zoom, pitch: 64, bearing, duration: 2600, curve: 1.1, essential: true })
        this.map.once('moveend', () => { if (gen === this.gen) this.orbit() })
      })
    } else {
      this.map.flyTo({ center: [lng, lat], zoom, pitch: 64, bearing, duration: 2800, curve: 1.3, essential: true })
      this.map.once('moveend', () => { if (gen === this.gen) this.orbit() })
    }
  }

  private orbit() {
    let last = performance.now()
    const step = (t: number) => {
      const dt = (t - last) / 1000
      last = t
      this.map.setBearing(this.map.getBearing() + dt * 4.5)
      this.orbitRaf = requestAnimationFrame(step)
    }
    this.orbitTimer = window.setTimeout(() => { this.orbitRaf = requestAnimationFrame(step) }, 300)
    this.stopTimer = window.setTimeout(() => this.interrupt(), 45_000)
  }
}
