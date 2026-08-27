/* One screen: the painting, a prompt line above it, the tools down the left
 * edge, and a status strip along the bottom. Everything else is a keystroke.
 */
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { Editor, isCutTool, type EditorStatus, type Tool } from './core/editor'
import { PAL, nameOf } from './core/mask'
import * as api from './api'
import { Icon, type IconName } from './ui/icons'

const TOOLS: { t: Tool; icon: IconName; key: string; label?: string; cut?: boolean }[] = [
  { t: 'brush', icon: 'brush', key: 'b' },
  { t: 'poly', icon: 'poly', key: 'p' },
  { t: 'rect', icon: 'rect', key: 'r' },
  { t: 'bucket', icon: 'bucket', key: 'f' },
  { t: 'eraser', icon: 'eraser', key: 'e' },
  { t: 'pick', icon: 'pick', key: 'i' },
  { t: 'occ', icon: 'occ', key: 'o' },
  { t: 'cut', icon: 'cut', key: 'c', label: 'cut brush', cut: true },
  { t: 'cuterase', icon: 'eraser', key: 'x', label: 'cut erase', cut: true },
  { t: 'cutfill', icon: 'bucket', key: 'v', label: 'cut fill, click a colour', cut: true },
  { t: 'cutpoly', icon: 'poly', key: 'n', label: 'cut polygon', cut: true },
]

interface Cand {
  id: string
  seed: number
  state: 'running' | 'done' | 'failed'
  url?: string
  error?: string
}

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .split('-')
    .slice(0, 4)
    .join('-') || 'scene'

export default function App() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const edRef = useRef<Editor | null>(null)
  const [st, setSt] = useState<EditorStatus | null>(null)
  const [prompt, setPrompt] = useState('')
  const [cands, setCands] = useState<Cand[]>([])
  const [usd, setUsd] = useState<string>('')

  // ---- editor ----------------------------------------------------------
  useEffect(() => {
    const ed = new Editor()
    edRef.current = ed
    let pending: EditorStatus | null = null
    let queued = false
    ed.onStatus((s) => {
      pending = s
      if (queued) return
      queued = true
      requestAnimationFrame(() => {
        queued = false
        if (pending) setSt(pending)
      })
    })
    ed.attach(canvasRef.current as HTMLCanvasElement)
    setSt(ed.status())

    const q = new URLSearchParams(location.search)
    const img = q.get('img')
    if (img) ed.loadPainting(img, q.get('id') || slug(img.split('/').pop() || 'scene')).catch(() => ed.say('could not load ' + img))

    return () => ed.detach()
  }, [])

  useEffect(() => {
    api
      .balance()
      .then((b) => setUsd(typeof b.usd === 'number' && b.usd > 0 ? `usd ${b.usd.toFixed(2)}` : ''))
      .catch(() => setUsd(''))
  }, [])

  const ed = edRef.current

  // ---- generate --------------------------------------------------------
  const run = useCallback(async () => {
    const e = edRef.current
    const p = prompt.trim()
    if (!e || !p) return
    const q = new URLSearchParams(location.search)
    const n = Number(q.get('n') || 4)
    const w = Number(q.get('w') || 688)
    const h = Number(q.get('h') || 384)
    e.setBusy(`generating ${n}`)
    setCands([])
    try {
      const { jobs } = await api.generate(p, n, w, h)
      const live: Cand[] = jobs
        .filter((j) => j.id)
        .map((j) => ({ id: j.id as string, seed: j.seed || 0, state: 'running' as const }))
      setCands(live)
      if (!live.length) {
        e.setBusy('')
        e.say(jobs[0]?.error || 'nothing came back')
        return
      }
      let left = live.length
      for (const c of live) {
        const poll = async () => {
          try {
            const s = await api.jobState(c.id)
            if (s.state === 'running') return setTimeout(poll, 5000)
            left--
            setCands((prev) =>
              prev.map((x) =>
                x.id === c.id
                  ? { ...x, state: s.state, url: s.images && s.images[0] ? 'data:image/png;base64,' + s.images[0] : undefined, error: s.error }
                  : x,
              ),
            )
          } catch (err) {
            left--
            setCands((prev) => prev.map((x) => (x.id === c.id ? { ...x, state: 'failed', error: String(err) } : x)))
          }
          e.setBusy(left > 0 ? `generating ${left}` : '')
        }
        setTimeout(poll, 4000)
      }
    } catch (err) {
      e.setBusy('')
      e.say(String(err instanceof Error ? err.message : err))
    }
  }, [prompt])

  const pick = useCallback(
    async (c: Cand) => {
      const e = edRef.current
      if (!e || !c.url) return
      const id = `${slug(prompt)}-${c.seed}`
      try {
        const { url } = await api.saveScene(id, c.url)
        await e.loadPainting(url, id)
      } catch {
        await e.loadPainting(c.url, id)
      }
    },
    [prompt],
  )

  // ---- the local first pass -------------------------------------------
  const doPropose = useCallback(async () => {
    const e = edRef.current
    if (!e) return
    const img = e.paintingDataURL()
    if (!img) return
    e.setBusy('reading the painting')
    try {
      const r = await api.propose(img)
      await e.applyLevelsPNG(r.levels)
      // the cut preview hides the levels overlay entirely, so a propose made
      // while it is on looks like nothing happened; flip back to the overlay
      const shown = e.revealLevels()
      e.say(
        `proposed ${r.note.pct ?? '?'}% walkable in ${r.note.seconds ?? '?'}s, now correct it` +
          (shown ? ' · overlay now shown' : ''),
      )
    } catch (err) {
      e.say(String(err instanceof Error ? err.message : err))
    }
    e.setBusy('')
  }, [])

  const doExport = useCallback(async () => {
    const e = edRef.current
    if (!e || !e.status().hasPainting) return
    e.setBusy('writing')
    try {
      const r = await api.exportBundle(e.bundle())
      e.say(`wrote ${r.files.join(', ')} to ${r.dir}`)
    } catch (err) {
      e.say(String(err instanceof Error ? err.message : err))
    }
    e.setBusy('')
  }, [])

  // the cut-applied painting on its own, before any mechanics are drawn
  const doSaveCut = useCallback(async () => {
    const e = edRef.current
    if (!e) return
    const img = e.cutSceneDataURL()
    if (!img) return
    e.setBusy('writing')
    try {
      const r = await api.saveCutPNG(e.status().sceneId, img, e.cutMaskDataURL())
      e.say(`wrote ${r.files.join(', ')} to ${r.dir}`)
    } catch (err) {
      e.say(String(err instanceof Error ? err.message : err))
    }
    e.setBusy('')
  }, [])

  const onDrop = useCallback((ev: DragEvent) => {
    ev.preventDefault()
    const f = ev.dataTransfer.files[0]
    const e = edRef.current
    if (!f || !e) return
    const fr = new FileReader()
    fr.onload = () => e.loadPainting(String(fr.result), slug(f.name.replace(/\.[a-z]+$/i, '')))
    fr.readAsDataURL(f)
  }, [])

  return (
    <div className="app">
      <header>
        <input
          value={prompt}
          placeholder="describe the map, press enter"
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') run()
            if (e.key === 'Escape') e.currentTarget.blur()
          }}
          spellCheck={false}
        />
        <span className="meta">
          {st?.hasPainting ? `${st.sceneId} ${st.w}x${st.h}` : 'no painting'}
          {st?.busy ? ` · ${st.busy}` : ''}
          {usd ? ` · ${usd}` : ''}
        </span>
      </header>

      {cands.length > 0 && (
        <div className="strip">
          {cands.map((c) => (
            <button
              key={c.id}
              className={'cand' + (c.state === 'running' ? ' wait' : '')}
              onClick={() => pick(c)}
              disabled={c.state !== 'done'}
              title={c.state === 'failed' ? c.error || 'failed' : `seed ${c.seed}`}
            >
              {c.url ? <img src={c.url} alt="" /> : <span>{c.state === 'failed' ? 'failed' : ''}</span>}
            </button>
          ))}
        </div>
      )}

      <main>
        <div className="tools">
          {TOOLS.map((t) => (
            <Fragment key={t.t}>
              {t.t === 'cut' && <div className="sep" />}
              <button
                className={(st?.tool === t.t ? 'on' : '') + (t.cut ? ' cut' : '')}
                onClick={() => ed?.setTool(t.t)}
                title={`${t.label || t.t} · ${t.key}`}
              >
                <Icon name={t.icon} />
              </button>
            </Fragment>
          ))}
          <button className="sparkle" onClick={doPropose} disabled={!st?.hasPainting} title="propose the walkable ground">
            <Icon name="sparkle" />
          </button>
          <div className="pal">
            {PAL.map((p) => (
              <button
                key={p.v}
                className={'chip' + (st?.value === p.v ? ' on' : '')}
                style={{ background: `rgb(${p.col.join(',')})` }}
                onClick={() => ed?.setValue(p.v)}
                title={`${p.name} · ${p.key}`}
              />
            ))}
          </div>
        </div>

        <div className="stage" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
          <canvas ref={canvasRef} />
          {!st?.hasPainting && <p className="empty">drop a png here, or describe the map above</p>}
          {st?.walking && <div className="walkbadge">walk test · wasd · space to stop</div>}
        </div>
      </main>

      <footer>
        <span className="read">
          {st && st.x >= 0 && st.hasPainting ? `${st.x},${st.y}` : ''}
          {st && st.level >= 0 ? ` ${nameOf(st.level)}` : ''}
          {st?.occ ? ` occ${st.occ}` : ''}
          {st?.cut ? ' cut' : ''}
        </span>
        <span className="read dim">
          {st?.hasPainting ? `${st.zoom}x · ${st.pct.toFixed(1)}% walkable` : ''}
          {st && st.occCount > 0 ? ` · ${st.occCount} occluder${st.occCount > 1 ? 's' : ''}` : ''}
          {st && st.cutPx > 0 ? ` · ${st.cutPx}px cut` : ''}
        </span>
        {st && st.occCount > 0 && (
          <label className="baseline">
            baseline
            <input
              type="number"
              value={st.lastBaseline}
              onChange={(e) => ed?.setBaseline(Number(e.target.value))}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === 'Escape') e.currentTarget.blur()
              }}
            />
          </label>
        )}
        {st?.tool === 'cutfill' && (
          <label className="cuttol" title="how far a colour may drift from the clicked pixel, 0-120">
            tol
            <input
              type="range"
              min={0}
              max={120}
              value={st.cutTol}
              onChange={(e) => ed?.setCutTol(Number(e.target.value))}
            />
            {st.cutTol}
          </label>
        )}
        <span className="note">{st?.note}</span>
        {st?.hasPainting && (
          <>
            <button
              className="cutbtn"
              onClick={() => ed?.autoSea()}
              title="cut the outer sea: floods from the border and the transparent edge at the current tolerance · inner tones are cut-fill clicks · one undo reverts it"
            >
              auto sea
            </button>
            <button
              className="cutbtn"
              onClick={() => ed?.despeckle()}
              title="keep the largest landmass, cut every floating speck · one undo reverts it"
            >
              despeckle
            </button>
            <button
              className="cutbtn"
              onClick={() => ed?.shaveEdge()}
              title="cut one pixel ring off the coast edge · one press per ring, undo steps back one press"
            >
              shave edge
            </button>
          </>
        )}
        {st && st.hasPainting && (st.cutPx > 0 || st.cutPreview || isCutTool(st.tool)) && (
          <>
            <button
              className={'cutbtn' + (st.cutPreview ? ' on' : '')}
              onClick={() => ed?.toggleCutPreview()}
              title="the painting with the cut applied, over a checkerboard · t"
            >
              cut view
            </button>
            <button className="cutbtn" onClick={doSaveCut} title="write the cut-applied painting as scene-cut.png">
              save cut png
            </button>
          </>
        )}
        <button onClick={() => ed?.heal()}>heal seams</button>
        <button onClick={() => ed?.check()}>check reach</button>
        <button onClick={() => ed?.setSpawnHere()}>set spawn</button>
        <button onClick={doExport}>export</button>
        <span className="read dim hint">space walks</span>
      </footer>
    </div>
  )
}
