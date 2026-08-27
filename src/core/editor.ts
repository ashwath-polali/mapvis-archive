/* The editor: one canvas, one painting, one mask on top of it.
 *
 * React owns the chrome (the prompt line, the tool strip, the bottom bar).
 * Everything that happens per frame or per pixel happens here, outside React,
 * so a brush stroke never runs a render pass.
 */
import { MaskDoc, PAL, colOf, mkCanvas, bresenham, type Pt } from './mask'
import { Walker, checkReach, defaultCfg, type WalkCfg, type ReachResult } from './walk'
import { savedScene } from '../api'

export type Tool =
  | 'brush'
  | 'poly'
  | 'rect'
  | 'bucket'
  | 'eraser'
  | 'pick'
  | 'occ'
  | 'cut'
  | 'cuterase'
  | 'cutfill'
  | 'cutpoly'

export const isCutTool = (t: Tool) => t === 'cut' || t === 'cuterase' || t === 'cutfill' || t === 'cutpoly'

export interface EditorStatus {
  x: number
  y: number
  level: number
  occ: number
  cut: number
  zoom: number
  walking: boolean
  walkable: number
  pct: number
  cutPx: number
  cutTol: number
  cutPreview: boolean
  tool: Tool
  value: number
  brush: number
  occCount: number
  lastBaseline: number
  note: string
  busy: string
  hasPainting: boolean
  sceneId: string
  w: number
  h: number
}

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))

export class Editor {
  doc = new MaskDoc(1, 1)
  cfg: WalkCfg = defaultCfg()
  walker = new Walker([0, 0])
  tool: Tool = 'brush'
  value = 40
  brush = 2
  opacity = 0.55
  showMask = true
  showOcc = true
  showHits = false
  grid = false
  walking = false
  cutTol = 40
  showCutPreview = false
  sceneId = 'untitled'
  note = ''
  busy = ''

  private canvas: HTMLCanvasElement | null = null
  private g: CanvasRenderingContext2D | null = null
  private painting: HTMLImageElement | HTMLCanvasElement | null = null
  private z = 3
  private ox = 0
  private oy = 0
  private dpr = 1
  private cursor: Pt | null = null
  private poly: Pt[] = []
  private dragRect: [number, number, number, number] | null = null
  private drawing = false
  private erasing = false
  private lastPx: Pt | null = null
  private panning: { sx: number; sy: number; ox: number; oy: number } | null = null
  private keys: Record<string, boolean> = {}
  private natMask: HTMLCanvasElement | null = null
  private natOcc: HTMLCanvasElement | null = null
  private natCut: HTMLCanvasElement | null = null
  private natHits: HTMLCanvasElement | null = null
  private pix: Uint8ClampedArray | null = null
  private cutApplied: HTMLCanvasElement | null = null
  private plates: { cv: HTMLCanvasElement; baseline: number }[] | null = null
  private dirtyMask = true
  private dirty = true
  private raf = 0
  private last = 0
  private saveT = 0
  private changed = false
  private listener: ((s: EditorStatus) => void) | null = null
  private detachers: (() => void)[] = []

  // ---- lifecycle --------------------------------------------------------
  attach(canvas: HTMLCanvasElement) {
    this.canvas = canvas
    this.g = canvas.getContext('2d')
    this.dpr = clamp(window.devicePixelRatio || 1, 1, 3)
    const ro = new ResizeObserver(() => this.resize())
    ro.observe(canvas.parentElement || canvas)
    this.detachers.push(() => ro.disconnect())

    const on = <K extends keyof HTMLElementEventMap>(
      t: HTMLElement | Window,
      k: K,
      f: (e: HTMLElementEventMap[K]) => void,
      opts?: AddEventListenerOptions,
    ) => {
      t.addEventListener(k, f as EventListener, opts)
      this.detachers.push(() => t.removeEventListener(k, f as EventListener, opts))
    }
    on(canvas, 'pointerdown', (e) => this.onDown(e as PointerEvent))
    on(canvas, 'pointermove', (e) => this.onMove(e as PointerEvent))
    on(canvas, 'pointerup', (e) => this.onUp(e as PointerEvent))
    on(canvas, 'pointerleave', () => {
      this.cursor = null
      this.dirty = true
    })
    on(canvas, 'dblclick', () => this.closePoly())
    on(canvas, 'contextmenu', (e) => e.preventDefault())
    on(canvas, 'wheel', (e) => this.onWheel(e as WheelEvent), { passive: false })
    on(window, 'keydown', (e) => this.onKey(e as KeyboardEvent, true))
    on(window, 'keyup', (e) => this.onKey(e as KeyboardEvent, false))
    on(window, 'blur', () => {
      this.keys = {}
    })

    // the scripting surface, the way tools/maskdraw exposed window.__md: the
    // console can drive every command the buttons drive
    ;(globalThis as unknown as { mapvis: Editor }).mapvis = this

    this.resize()
    this.last = performance.now()
    // scheduled first, so one bad frame cannot stop the tool dead
    const loop = (now: number) => {
      this.raf = requestAnimationFrame(loop)
      this.frame(now)
    }
    this.raf = requestAnimationFrame(loop)
  }

  detach() {
    cancelAnimationFrame(this.raf)
    for (const d of this.detachers) d()
    this.detachers = []
  }

  onStatus(cb: (s: EditorStatus) => void) {
    this.listener = cb
  }

  status(): EditorStatus {
    const s = this.doc.stats()
    const c = this.cursor
    const lastOcc = this.doc.occs[this.doc.occs.length - 1]
    return {
      x: c ? c[0] : -1,
      y: c ? c[1] : -1,
      level: c ? this.doc.lvlAt(c[0], c[1]) : -1,
      occ: c ? this.doc.occAt(c[0], c[1]) : 0,
      cut: c ? this.doc.cutAt(c[0], c[1]) : 0,
      zoom: this.z,
      walking: this.walking,
      walkable: s.walkable,
      pct: s.pct,
      cutPx: s.cut,
      cutTol: this.cutTol,
      cutPreview: this.showCutPreview,
      tool: this.tool,
      value: this.value,
      brush: this.brush,
      occCount: this.doc.occs.length,
      lastBaseline: lastOcc ? lastOcc.baseline : 0,
      note: this.note,
      busy: this.busy,
      hasPainting: !!this.painting,
      sceneId: this.sceneId,
      w: this.doc.W,
      h: this.doc.H,
    }
  }
  private emit() {
    if (this.listener) this.listener(this.status())
  }
  say(note: string) {
    this.note = note
    this.emit()
  }
  setBusy(b: string) {
    this.busy = b
    this.emit()
  }

  // ---- the painting -----------------------------------------------------
  async loadPainting(src: string, id: string) {
    const img = await loadImage(src)
    this.painting = img
    this.sceneId = id
    this.doc = new MaskDoc(img.naturalWidth, img.naturalHeight)
    this.walker = new Walker(this.doc.spawn)
    this.natMask = mkCanvas(this.doc.W, this.doc.H)
    this.natOcc = mkCanvas(this.doc.W, this.doc.H)
    this.natCut = mkCanvas(this.doc.W, this.doc.H)
    this.natHits = mkCanvas(this.doc.W, this.doc.H)
    this.plates = null
    this.cutApplied = null
    // the painting's own pixels, read once: the cut flood matches against these
    {
      const c = mkCanvas(this.doc.W, this.doc.H)
      const g = c.getContext('2d') as CanvasRenderingContext2D
      g.drawImage(img, 0, 0)
      this.pix = g.getImageData(0, 0, this.doc.W, this.doc.H).data
    }
    if (!this.restoreLocal()) await this.restoreFromDisk()
    this.fit()
    this.dirtyMask = true
    this.dirty = true
    this.emit()
  }

  paintingDataURL(): string | null {
    if (!this.painting) return null
    const c = mkCanvas(this.doc.W, this.doc.H)
    const g = c.getContext('2d') as CanvasRenderingContext2D
    g.drawImage(this.painting, 0, 0)
    return c.toDataURL('image/png')
  }

  fit() {
    if (!this.canvas || !this.painting) return
    const cw = this.canvas.clientWidth
    const ch = this.canvas.clientHeight
    const z = clamp(Math.floor(Math.min(cw / this.doc.W, ch / this.doc.H)), 1, 8)
    this.z = z || 1
    this.ox = Math.round((cw - this.doc.W * this.z) / 2)
    this.oy = Math.round((ch - this.doc.H * this.z) / 2)
    this.dirty = true
  }

  setZoom(z: number, cx?: number, cy?: number) {
    if (!this.canvas) return
    const nz = clamp(Math.round(z), 1, 8)
    const px = cx == null ? this.canvas.clientWidth / 2 : cx
    const py = cy == null ? this.canvas.clientHeight / 2 : cy
    const nx = (px - this.ox) / this.z
    const ny = (py - this.oy) / this.z
    this.z = nz
    this.ox = Math.round(px - nx * nz)
    this.oy = Math.round(py - ny * nz)
    this.dirty = true
    this.emit()
  }

  private resize() {
    const c = this.canvas
    if (!c || !this.g) return
    const w = c.clientWidth
    const h = c.clientHeight
    c.width = Math.max(1, Math.round(w * this.dpr))
    c.height = Math.max(1, Math.round(h * this.dpr))
    this.g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this.g.imageSmoothingEnabled = false
    this.dirty = true
  }

  // ---- input ------------------------------------------------------------
  private toNative(e: PointerEvent | WheelEvent): Pt {
    const r = (this.canvas as HTMLCanvasElement).getBoundingClientRect()
    return [
      Math.floor((e.clientX - r.left - this.ox) / this.z),
      Math.floor((e.clientY - r.top - this.oy) / this.z),
    ]
  }

  // a synthesised pointer has no id the browser will capture, and scripts use
  // synthesised pointers
  private capture(e: PointerEvent) {
    try {
      ;(this.canvas as HTMLCanvasElement).setPointerCapture(e.pointerId)
    } catch {
      /* scripted pointer */
    }
  }

  private onDown(e: PointerEvent) {
    if (!this.painting) return
    const r = (this.canvas as HTMLCanvasElement).getBoundingClientRect()
    if (e.button === 1 || e.altKey) {
      this.panning = { sx: e.clientX, sy: e.clientY, ox: this.ox, oy: this.oy }
      this.capture(e)
      e.preventDefault()
      return
    }
    if (this.walking) return
    const [x, y] = this.toNative(e)
    this.lastPx = [x, y]
    void r
    const erase = e.shiftKey || e.button === 2 || this.tool === 'eraser'
    if (this.tool === 'pick') {
      this.value = this.doc.lvlAt(x, y)
      this.emit()
      return
    }
    if (this.tool === 'poly' || this.tool === 'occ' || this.tool === 'cutpoly') {
      this.poly.push([x + 0.5, y + 0.5])
      this.dirty = true
      return
    }
    if (this.tool === 'bucket') {
      this.doc.snap()
      this.doc.bucket(x, y, erase ? 0 : this.value)
      this.touched()
      return
    }
    if (this.tool === 'cutfill') {
      if (!this.pix || !this.doc.inB(x, y)) return
      this.doc.snap()
      const n = this.doc.cutFlood(x, y, erase ? 0 : 1, this.cutTol, this.pix)
      this.touched()
      this.say(`${erase ? 'uncut' : 'cut'} ${n}px, tolerance ${this.cutTol}`)
      return
    }
    if (this.tool === 'rect') {
      this.doc.snap()
      this.dragRect = [x, y, x, y]
      this.erasing = erase
      this.capture(e)
      return
    }
    this.doc.snap()
    this.drawing = true
    this.erasing = erase
    if (this.tool === 'cut' || this.tool === 'cuterase')
      this.doc.cutStamp(x, y, this.tool === 'cuterase' || erase ? 0 : 1, this.brush)
    else this.doc.stamp(x, y, erase ? 0 : this.value, this.brush)
    ;(this.canvas as HTMLCanvasElement).setPointerCapture(e.pointerId)
    this.touched()
  }

  private onMove(e: PointerEvent) {
    if (this.panning) {
      this.ox = this.panning.ox + (e.clientX - this.panning.sx)
      this.oy = this.panning.oy + (e.clientY - this.panning.sy)
      this.dirty = true
      return
    }
    if (!this.painting) return
    const [x, y] = this.toNative(e)
    this.cursor = [x, y]
    if (this.drawing) {
      const [px, py] = this.lastPx || [x, y]
      if (this.tool === 'cut' || this.tool === 'cuterase') {
        const cv = this.tool === 'cuterase' || this.erasing ? 0 : 1
        bresenham(px, py, x, y, (cx, cy) => this.doc.cutStamp(cx, cy, cv, this.brush))
      } else {
        const v = this.erasing ? 0 : this.value
        bresenham(px, py, x, y, (cx, cy) => this.doc.stamp(cx, cy, v, this.brush))
      }
      this.touched()
    }
    if (this.dragRect) {
      this.dragRect[2] = x
      this.dragRect[3] = y
    }
    this.lastPx = [x, y]
    this.dirty = true
    this.emit()
  }

  private onUp(_e: PointerEvent) {
    this.panning = null
    if (this.dragRect) {
      const [a, b, c, d] = this.dragRect
      this.doc.fillRect(a, b, c, d, this.erasing ? 0 : this.value)
      this.dragRect = null
      this.touched()
    }
    this.drawing = false
  }

  private onWheel(e: WheelEvent) {
    if (!this.painting) return
    e.preventDefault()
    const r = (this.canvas as HTMLCanvasElement).getBoundingClientRect()
    this.setZoom(this.z + (e.deltaY < 0 ? 1 : -1), e.clientX - r.left, e.clientY - r.top)
  }

  private onKey(e: KeyboardEvent, down: boolean) {
    const t = e.target as HTMLElement | null
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return
    const k = e.key.toLowerCase()
    this.keys[k] = down
    if (!down) return
    if (k === ' ') {
      e.preventDefault()
      this.toggleWalk()
      return
    }
    if (this.walking && ['arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) {
      e.preventDefault()
      return
    }
    const p = PAL.find((q) => q.key === e.key)
    if (p) {
      this.value = p.v
      this.emit()
      return
    }
    if (k === 'z' && !this.walking) {
      if (this.doc.undo()) this.touched()
      return
    }
    if (k === 'b') this.setTool('brush')
    else if (k === 'p') this.setTool('poly')
    else if (k === 'r') this.setTool('rect')
    else if (k === 'f') this.setTool('bucket')
    else if (k === 'e') this.setTool('eraser')
    else if (k === 'i') this.setTool('pick')
    else if (k === 'o') this.setTool('occ')
    else if (k === 'c') this.setTool('cut')
    else if (k === 'x') this.setTool('cuterase')
    else if (k === 'v') this.setTool('cutfill')
    else if (k === 'n') this.setTool('cutpoly')
    else if (k === 't') this.toggleCutPreview()
    else if (k === 'g') {
      this.grid = !this.grid
      this.dirty = true
    } else if (k === 'm') {
      this.showMask = !this.showMask
      this.dirtyMask = true
    } else if (k === 'h') {
      this.showHits = !this.showHits
      this.dirtyMask = true
    } else if (e.key === 'Enter') this.closePoly()
    else if (e.key === 'Escape') {
      this.poly = []
      this.dirty = true
    } else if (e.key === 'Backspace') {
      this.poly.pop()
      this.dirty = true
      e.preventDefault()
    } else if (k === '[') this.setBrush(this.brush - 1)
    else if (k === ']') this.setBrush(this.brush + 1)
    else if (k === '+' || k === '=') this.setZoom(this.z + 1)
    else if (k === '-') this.setZoom(this.z - 1)
  }

  // ---- commands ---------------------------------------------------------
  setTool(t: Tool) {
    this.tool = t
    this.poly = []
    this.dirty = true
    this.emit()
  }
  setValue(v: number) {
    this.value = v
    this.emit()
  }
  setBrush(n: number) {
    this.brush = clamp(n, 1, 16)
    this.dirty = true
    this.emit()
  }
  setBaseline(y: number) {
    const o = this.doc.occs[this.doc.occs.length - 1]
    if (!o) return
    o.baseline = Math.round(y)
    this.plates = null
    this.emit()
  }
  closePoly() {
    if (this.poly.length < 3) {
      this.poly = []
      this.dirty = true
      return
    }
    this.doc.snap()
    if (this.tool === 'occ') {
      const o = this.doc.addOccluder(this.poly)
      this.plates = null
      this.say(`occluder ${o.id}, baseline y ${o.baseline}`)
    } else if (this.tool === 'cutpoly') {
      this.doc.fillPoly(this.poly, 1, 'cut')
    } else {
      this.doc.fillPoly(this.poly, this.value, 'lvl')
    }
    this.poly = []
    this.touched()
  }
  setCutTol(n: number) {
    this.cutTol = clamp(Math.round(n), 0, 120)
    this.emit()
  }
  // every cut-fill click a human would make along the border and the
  // transparent edge, made at once. One snapshot first, so one undo takes the
  // whole proposal back. FIXED tolerance, never the slider: at a raised manual
  // tolerance the margin floods walked from sea navy into island rock and
  // proposed half the island (Ash hit this 2026-08-15). One press must behave
  // the same every time; wider grabs belong to the human's cut-fill clicks.
  autoSea() {
    if (!this.pix || !this.painting) return
    this.doc.snap()
    const n = this.doc.autoSea(40, this.pix)
    this.touched()
    this.say(`auto sea: ${n} px proposed, correct it`)
  }
  // one landmass rule: every 4-way component of uncut opaque pixels except
  // the largest joins the cut. One snapshot, one undo.
  despeckle() {
    if (!this.pix || !this.painting) return
    this.doc.snap()
    const r = this.doc.despeckle(this.pix)
    if (!r.specks) {
      // nothing changed, so drop the identical snapshot and keep z meaningful
      this.doc.undo()
      this.say('despeckle: nothing to remove')
      return
    }
    this.touched()
    this.say(`despeckle: cut ${r.px} px in ${r.specks} specks`)
  }
  // one dilation ring per press: the anti-aliased coast fringe is a single
  // pixel of blended tone, so each press eats exactly one ring and one undo
  // gives exactly one ring back.
  shaveEdge() {
    if (!this.pix || !this.painting) return
    this.doc.snap()
    const n = this.doc.shaveEdge(this.pix)
    this.touched()
    this.say(`shaved ${n} px off the edge`)
  }
  toggleCutPreview() {
    this.showCutPreview = !this.showCutPreview
    this.dirty = true
    this.emit()
  }
  // After a propose, the result must actually be on screen: the cut preview
  // replaces the whole draw with the cut-applied painting, and m can have
  // hidden the levels overlay. Returns true when something had to be flipped,
  // so the caller can say the overlay is now shown.
  revealLevels(): boolean {
    let changed = false
    if (this.showCutPreview) {
      this.showCutPreview = false
      changed = true
    }
    if (!this.showMask) {
      this.showMask = true
      changed = true
    }
    if (changed) {
      this.dirtyMask = true
      this.dirty = true
      this.emit()
    }
    return changed
  }
  toggleWalk() {
    this.walking = !this.walking
    if (this.walking) {
      this.walker = new Walker(this.doc.spawn)
      this.plates = null
    }
    this.dirty = true
    this.emit()
  }
  setSpawnHere() {
    if (this.walking) this.doc.spawn = [Math.round(this.walker.x), Math.round(this.walker.y)]
    else if (this.cursor) this.doc.spawn = [this.cursor[0], this.cursor[1]]
    this.dirty = true
    this.say(`spawn ${this.doc.spawn[0]}, ${this.doc.spawn[1]}`)
  }
  clearMask() {
    this.doc.clear()
    this.plates = null
    this.touched()
    this.say('mask cleared')
  }
  heal() {
    this.doc.snap()
    const r = this.doc.healSeams(this.cfg.near)
    this.touched()
    this.say(`healed ${r.filled} seam px in ${r.passes} pass${r.passes > 1 ? 'es' : ''}`)
  }
  check(): ReachResult {
    const r = checkReach(this.doc, this.cfg)
    this.showHits = true
    this.touched()
    this.say(
      r.orphans.length
        ? `reached ${r.reached}px · cut off: ` +
            r.orphans
              .slice(0, 3)
              .map((o) => `${o.px}px at ${o.rect[0]},${o.rect[1]}`)
              .join(' · ')
        : `reached ${r.reached}px · nothing is cut off`,
    )
    return r
  }
  applyLevelsPNG(dataURL: string) {
    return loadImage(dataURL).then((img) => {
      this.doc.importLevels(img)
      this.touched()
    })
  }
  // the painting with the cut applied: cut pixels at alpha 0, art untouched.
  // This is what the engine gets, and what the preview shows.
  private buildCutApplied(): HTMLCanvasElement {
    const c = mkCanvas(this.doc.W, this.doc.H)
    const g = c.getContext('2d') as CanvasRenderingContext2D
    if (this.painting) g.drawImage(this.painting, 0, 0)
    const d = g.getImageData(0, 0, this.doc.W, this.doc.H)
    for (let i = 0; i < this.doc.cut.length; i++) if (this.doc.cut[i]) d.data[i * 4 + 3] = 0
    g.putImageData(d, 0, 0)
    return c
  }
  cutSceneDataURL(): string | null {
    if (!this.painting) return null
    return this.buildCutApplied().toDataURL('image/png')
  }
  cutMaskDataURL(): string {
    return this.doc.cutCanvas().toDataURL('image/png')
  }
  bundle() {
    const hasCut = this.doc.stats().cut > 0
    const scene = hasCut ? this.buildCutApplied() : mkCanvas(this.doc.W, this.doc.H)
    if (!hasCut) {
      const sg = scene.getContext('2d') as CanvasRenderingContext2D
      if (this.painting) sg.drawImage(this.painting, 0, 0)
    }
    return {
      id: this.sceneId,
      scene: scene.toDataURL('image/png'),
      levels: this.doc.levelsCanvas(hasCut ? this.doc.cut : undefined).toDataURL('image/png'),
      cut: hasCut ? this.doc.cutCanvas().toDataURL('image/png') : null,
      occluders: this.doc.occludersCanvas().toDataURL('image/png'),
      map: {
        id: this.sceneId,
        w: this.doc.W,
        h: this.doc.H,
        encoding: {
          blocked: 0,
          L0: 40,
          ramp01: 50,
          L1: 60,
          ramp12: 70,
          L2: 80,
          ramp23: 90,
          L3: 100,
          stepTolerance: this.cfg.near,
        },
        spawn: this.doc.spawn,
        character: { heightPx: this.cfg.charH, hip: this.cfg.hip, hipDY: this.cfg.hipDY },
        speed: this.cfg.speed,
        yScale: this.cfg.yScale,
        stairs: this.doc.stairRegions(),
        occluders: this.doc.occs.map((o) => ({ id: o.id, baseline: o.baseline })),
      },
    }
  }

  private touched() {
    this.dirtyMask = true
    this.dirty = true
    this.changed = true
    this.cutApplied = null
    this.emit()
  }

  // ---- local autosave, silent -------------------------------------------
  private key() {
    return `mapvis:${this.sceneId}:${this.doc.W}x${this.doc.H}`
  }
  private saveLocal() {
    try {
      localStorage.setItem(this.key(), this.doc.serialize())
      localStorage.setItem(this.key() + ':meta', JSON.stringify({ spawn: this.doc.spawn }))
    } catch {
      /* a full quota is not worth an error in the face */
    }
  }
  private restoreLocal() {
    try {
      const d = localStorage.getItem(this.key())
      if (d && this.doc.deserialize(d)) {
        const m = localStorage.getItem(this.key() + ':meta')
        if (m) this.doc.spawn = JSON.parse(m).spawn
        this.say('restored the mask from this browser')
        return true
      }
    } catch {
      /* nothing saved, or nothing readable */
    }
    return false
  }

  // an exported bundle is the other place a mask lives, so reopening a scene
  // that was exported under this id picks it back up
  private async restoreFromDisk() {
    try {
      const s = await savedScene(this.sceneId)
      let got = false
      if (s.cut) {
        this.doc.importCut(await loadImage(s.cut))
        got = true
      }
      if (s.levels) {
        this.doc.importLevels(await loadImage(s.levels))
        if (s.occluders && s.map && s.map.occluders && s.map.occluders.length)
          this.doc.importOccluders(await loadImage(s.occluders), s.map.occluders)
        if (s.map && s.map.spawn) this.doc.spawn = s.map.spawn
        got = true
      }
      if (got) this.say(`reopened the mask from work/${this.sceneId}`)
    } catch {
      /* never exported, or the api is not up */
    }
  }

  // ---- render -----------------------------------------------------------
  private bakeLayers() {
    if (!this.natMask || !this.natOcc || !this.natCut || !this.natHits) return
    const { W, H } = this.doc
    const gm = (this.natMask as HTMLCanvasElement).getContext('2d') as CanvasRenderingContext2D
    const d = gm.createImageData(W, H)
    const p = d.data
    for (let i = 0; i < this.doc.lvl.length; i++) {
      const v = this.doc.lvl[i]
      const c = colOf(v)
      p[i * 4] = c[0]
      p[i * 4 + 1] = c[1]
      p[i * 4 + 2] = c[2]
      p[i * 4 + 3] = v === 0 ? 0 : 255
    }
    gm.putImageData(d, 0, 0)

    const go = (this.natOcc as HTMLCanvasElement).getContext('2d') as CanvasRenderingContext2D
    const o = go.createImageData(W, H)
    const q = o.data
    for (let i = 0; i < this.doc.occ.length; i++) {
      if (!this.doc.occ[i]) continue
      q[i * 4] = 190
      q[i * 4 + 1] = 120
      q[i * 4 + 2] = 255
      q[i * 4 + 3] = 150
    }
    go.putImageData(o, 0, 0)

    // the cut layer: a magenta 1px checker, deliberately not a colour any
    // painting uses, so a cut pixel can never be mistaken for art
    const gc = (this.natCut as HTMLCanvasElement).getContext('2d') as CanvasRenderingContext2D
    const cd = gc.createImageData(W, H)
    const cp = cd.data
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++) {
        const i = y * W + x
        if (!this.doc.cut[i]) continue
        cp[i * 4] = 255
        cp[i * 4 + 1] = 64
        cp[i * 4 + 2] = 208
        cp[i * 4 + 3] = (x + y) & 1 ? 190 : 80
      }
    gc.putImageData(cd, 0, 0)

    const gh = (this.natHits as HTMLCanvasElement).getContext('2d') as CanvasRenderingContext2D
    const h = gh.createImageData(W, H)
    const r = h.data
    for (let i = 0; i < this.doc.hits.length; i++) {
      if (!this.doc.hits[i]) continue
      r[i * 4] = 255
      r[i * 4 + 1] = 40
      r[i * 4 + 2] = 40
      r[i * 4 + 3] = Math.min(255, this.doc.hits[i] * 24)
    }
    gh.putImageData(h, 0, 0)
    this.dirtyMask = false
  }

  // An occluder is a piece of the painting lifted back out of it and drawn
  // over the character when his feet are north of its baseline. Baking it from
  // the painting itself is what keeps it pixel-identical to the art.
  private bakePlates() {
    const { W, H } = this.doc
    this.plates = this.doc.occs.map((o) => {
      const c = mkCanvas(W, H)
      const g = c.getContext('2d') as CanvasRenderingContext2D
      if (this.painting) g.drawImage(this.painting, 0, 0)
      const d = g.getImageData(0, 0, W, H)
      for (let i = 0; i < this.doc.occ.length; i++) if (this.doc.occ[i] !== o.id) d.data[i * 4 + 3] = 0
      g.putImageData(d, 0, 0)
      return { cv: c, baseline: o.baseline }
    })
  }

  private frame(now: number) {
    const dt = Math.min(50, now - this.last) / 1000
    this.last = now
    if (this.walking) {
      const wasBlocked = this.walker.step(this.doc, this.cfg, this.keys, dt)
      if (wasBlocked && this.showHits) this.dirtyMask = true
      this.dirty = true
    }
    if (this.changed && now - this.saveT > 4000) {
      this.saveLocal()
      this.changed = false
      this.saveT = now
    }
    if (!this.dirty && !this.dirtyMask) return
    if (this.dirtyMask) this.bakeLayers()
    this.draw()
    this.dirty = false
  }

  private draw() {
    const g = this.g
    const c = this.canvas
    if (!g || !c) return
    const cw = c.clientWidth
    const ch = c.clientHeight
    g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    g.imageSmoothingEnabled = false
    g.clearRect(0, 0, cw, ch)
    if (!this.painting) return
    const { W, H } = this.doc
    const z = this.z
    const ox = Math.round(this.ox)
    const oy = Math.round(this.oy)
    const w = W * z
    const h = H * z

    g.save()
    g.translate(ox, oy)
    if (this.showCutPreview) {
      // exactly what the game will get: the painting with the cut applied,
      // over a dark checkerboard where the engine's ocean will show through
      const B = 8 * z
      g.fillStyle = '#101318'
      g.fillRect(0, 0, w, h)
      g.fillStyle = '#191d24'
      for (let by = 0; by * B < h; by++)
        for (let bx = (by & 1); bx * B < w; bx += 2)
          g.fillRect(bx * B, by * B, Math.min(B, w - bx * B), Math.min(B, h - by * B))
      if (!this.cutApplied) this.cutApplied = this.buildCutApplied()
      g.drawImage(this.cutApplied, 0, 0, w, h)
    } else {
      g.drawImage(this.painting, 0, 0, w, h)
      if (this.showMask && this.natMask) {
        g.globalAlpha = this.opacity
        g.drawImage(this.natMask, 0, 0, w, h)
        g.globalAlpha = 1
      }
      if (this.showOcc && this.natOcc) g.drawImage(this.natOcc, 0, 0, w, h)
      if (this.natCut) g.drawImage(this.natCut, 0, 0, w, h)
      if (this.showHits && this.natHits) g.drawImage(this.natHits, 0, 0, w, h)
    }

    if (this.grid && z >= 4) {
      g.strokeStyle = 'rgba(255,255,255,0.09)'
      g.lineWidth = 1
      g.beginPath()
      for (let x = 0; x <= W; x++) {
        g.moveTo(x * z + 0.5, 0)
        g.lineTo(x * z + 0.5, h)
      }
      for (let y = 0; y <= H; y++) {
        g.moveTo(0, y * z + 0.5)
        g.lineTo(w, y * z + 0.5)
      }
      g.stroke()
    }
    if (this.poly.length) {
      const pc = this.tool === 'occ' ? '#c07aff' : this.tool === 'cutpoly' ? '#ff40d0' : '#ffd166'
      g.strokeStyle = pc
      g.lineWidth = 1.5
      g.beginPath()
      this.poly.forEach((p, i) => (i ? g.lineTo(p[0] * z, p[1] * z) : g.moveTo(p[0] * z, p[1] * z)))
      if (this.cursor) g.lineTo((this.cursor[0] + 0.5) * z, (this.cursor[1] + 0.5) * z)
      g.stroke()
      g.fillStyle = this.tool === 'cutpoly' ? '#ff40d0' : '#ffd166'
      for (const p of this.poly) g.fillRect(p[0] * z - 1.5, p[1] * z - 1.5, 3, 3)
    }
    if (this.dragRect) {
      const [a, b, cx, cy] = this.dragRect
      g.strokeStyle = '#ffd166'
      g.lineWidth = 1
      g.strokeRect(
        Math.min(a, cx) * z + 0.5,
        Math.min(b, cy) * z + 0.5,
        (Math.abs(cx - a) + 1) * z - 1,
        (Math.abs(cy - b) + 1) * z - 1,
      )
    }
    // the brush footprint: exactly which native pixels the next click changes
    if (
      this.cursor &&
      !this.walking &&
      (this.tool === 'brush' || this.tool === 'eraser' || this.tool === 'cut' || this.tool === 'cuterase')
    ) {
      const h0 = Math.floor((this.brush - 1) / 2)
      g.strokeStyle = this.tool === 'cut' || this.tool === 'cuterase' ? '#ff40d0' : '#ffffff'
      g.lineWidth = 1
      g.strokeRect((this.cursor[0] - h0) * z + 0.5, (this.cursor[1] - h0) * z + 0.5, this.brush * z - 1, this.brush * z - 1)
    }
    g.strokeStyle = '#6fd08c'
    g.lineWidth = 1
    g.strokeRect(this.doc.spawn[0] * z - 2, this.doc.spawn[1] * z - 2, 5, 5)

    if (this.walking) {
      this.drawWalker(g)
      if (this.doc.occs.length) {
        if (!this.plates) this.bakePlates()
        for (const p of this.plates as { cv: HTMLCanvasElement; baseline: number }[])
          if (this.walker.y < p.baseline) g.drawImage(p.cv, 0, 0, w, h)
      }
    }
    g.restore()

    // frame edge, so the painting's bounds are readable against the backdrop
    g.strokeStyle = 'rgba(255,255,255,0.14)'
    g.lineWidth = 1
    g.strokeRect(ox - 0.5, oy - 0.5, w + 1, h + 1)
  }

  private drawWalker(g: CanvasRenderingContext2D) {
    const z = this.z
    const W = this.walker
    const px = W.x * z
    const py = W.y * z
    const bodyH = this.cfg.charH * z
    const bodyW = Math.max(3, this.cfg.hip * 2 * z)
    g.save()
    g.fillStyle = 'rgba(6,10,14,0.42)'
    g.beginPath()
    g.ellipse(px, py, bodyW * 0.8, bodyW * 0.3, 0, 0, 6.284)
    g.fill()
    g.fillStyle = W.blocked ? '#ffb3c0' : '#e9edf3'
    g.fillRect(px - bodyW / 2, py - bodyH, bodyW, bodyH)
    g.fillStyle = '#0e1116'
    g.fillRect(px - bodyW / 2, py - bodyH, bodyW, Math.max(1, bodyH * 0.22))
    g.restore()
    // the collision pixel and the two hip probes, drawn at native scale
    g.fillStyle = W.blocked ? '#ff3040' : '#40ff90'
    g.fillRect(Math.round(W.x) * z, Math.round(W.y) * z, z, z)
    g.fillStyle = '#40c8ff'
    g.fillRect(Math.round(W.x - this.cfg.hip) * z, Math.round(W.y - this.cfg.hipDY) * z, z, z)
    g.fillRect(Math.round(W.x + this.cfg.hip) * z, Math.round(W.y - this.cfg.hipDY) * z, z, z)
  }
}

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((res, rej) => {
    const i = new Image()
    i.onload = () => res(i)
    i.onerror = () => rej(new Error('could not load ' + src.slice(0, 80)))
    i.src = src
  })
}
