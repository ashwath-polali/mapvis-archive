/* The local api. It exists so the pixellab token stays in node, and so the SAM
 * pass can run against the GPU. It is mounted into the vite dev server, so
 * `npm run dev` is one command and one port.
 *
 *   GET  /api/balance          what is left on the pixellab account
 *   POST /api/generate         { prompt, n } -> job ids
 *   GET  /api/job/:id          running | done + images | failed
 *   POST /api/propose          { image } -> a rough levels png from SAM
 *   POST /api/export           writes the bundle into work/<id>/
 *   POST /api/savecut          writes scene-cut.png + cut.png into work/<id>/
 *   GET  /work/<path>          serves what is in work/
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import * as pixellab from './pixellab.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')
const WORK = path.join(ROOT, 'work')

const PYTHON =
  process.env.MAPVIS_PYTHON || 'C:\\Users\\ashcy\\ComfyUI_windows_portable\\python_embeded\\python.exe'
const SAM_CKPT =
  process.env.MAPVIS_SAM_CKPT || 'C:\\Users\\ashcy\\AdventureGame\\.tmp_extract\\sam_vit_b_01ec64.pth'

const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json' }

export function api(req, res, next) {
  const url = new URL(req.url, 'http://local')
  const p = url.pathname
  if (!p.startsWith('/api/') && !p.startsWith('/work/')) return next ? next() : notFound(res)
  Promise.resolve(route(req, res, p, url)).catch((e) => send(res, 500, { error: String(e.message || e) }))
}

async function route(req, res, p, url) {
  if (p.startsWith('/work/')) return serveWork(res, p.slice('/work/'.length))
  if (p === '/api/balance') return send(res, 200, await pixellab.balance())

  if (p === '/api/generate' && req.method === 'POST') {
    const b = await body(req)
    const prompt = String(b.prompt || '').trim()
    if (!prompt) return send(res, 400, { error: 'no prompt' })
    const n = Math.max(1, Math.min(6, b.n || 4))
    const w = b.w || 688
    const h = b.h || 384
    const jobs = []
    for (let i = 0; i < n; i++) {
      const seed = Math.floor(Math.random() * 1e9)
      try {
        jobs.push({ id: await pixellab.submit({ prompt, w, h, seed }), seed })
      } catch (e) {
        jobs.push({ error: String(e.message || e).slice(0, 200) })
      }
    }
    return send(res, 200, { jobs, w, h })
  }

  if (p.startsWith('/api/job/')) {
    return send(res, 200, await pixellab.job(decodeURIComponent(p.slice('/api/job/'.length))))
  }

  if (p === '/api/propose' && req.method === 'POST') {
    const b = await body(req)
    if (!b.image) return send(res, 400, { error: 'no image' })
    const dir = path.join(WORK, '.propose')
    fs.mkdirSync(dir, { recursive: true })
    const inPath = path.join(dir, 'in.png')
    const outPath = path.join(dir, 'levels.png')
    fs.writeFileSync(inPath, Buffer.from(stripDataURL(b.image), 'base64'))
    if (fs.existsSync(outPath)) fs.unlinkSync(outPath)
    if (!fs.existsSync(PYTHON)) return send(res, 500, { error: `no python at ${PYTHON}` })
    if (!fs.existsSync(SAM_CKPT)) return send(res, 500, { error: `no sam checkpoint at ${SAM_CKPT}` })
    const out = await run(PYTHON, [
      path.join(HERE, 'propose_sam.py'),
      '--image',
      inPath,
      '--out',
      outPath,
      '--checkpoint',
      SAM_CKPT,
    ])
    if (!fs.existsSync(outPath)) return send(res, 500, { error: (out.err || out.out || 'sam wrote nothing').slice(-300) })
    let note = {}
    try {
      note = JSON.parse((out.out.trim().split('\n').pop() || '{}'))
    } catch {
      note = {}
    }
    return send(res, 200, {
      levels: 'data:image/png;base64,' + fs.readFileSync(outPath).toString('base64'),
      note,
    })
  }

  // reopening a map: whatever was exported under this id, as data urls. Always
  // 200, so a map that was never exported does not put a 404 in the console.
  if (p.startsWith('/api/scene/')) {
    const dir = path.join(WORK, safeId(decodeURIComponent(p.slice('/api/scene/'.length))))
    const out = {}
    const png = (n) => {
      const f = path.join(dir, n)
      return fs.existsSync(f) ? 'data:image/png;base64,' + fs.readFileSync(f).toString('base64') : null
    }
    // the cut can exist before any mechanics do: a painting is cut and staged,
    // then the levels are drawn later
    out.cut = png('cut.png')
    const mapFile = path.join(dir, 'map.json')
    if (fs.existsSync(mapFile)) {
      try {
        out.map = JSON.parse(fs.readFileSync(mapFile, 'utf8'))
      } catch {
        out.map = null
      }
      out.levels = png('levels.png')
      out.occluders = png('occluders.png')
    }
    return send(res, 200, out)
  }

  if (p === '/api/export' && req.method === 'POST') {
    const b = await body(req)
    const id = safeId(b.id)
    const dir = path.join(WORK, id)
    fs.mkdirSync(dir, { recursive: true })
    const files = []
    for (const [name, data] of [
      ['scene.png', b.scene],
      ['levels.png', b.levels],
      ['occluders.png', b.occluders],
      ['cut.png', b.cut],
    ]) {
      if (!data) continue
      fs.writeFileSync(path.join(dir, name), Buffer.from(stripDataURL(data), 'base64'))
      files.push(name)
    }
    // a cut that was erased back to nothing should not survive on disk
    if (!b.cut && fs.existsSync(path.join(dir, 'cut.png'))) fs.unlinkSync(path.join(dir, 'cut.png'))
    fs.writeFileSync(path.join(dir, 'map.json'), JSON.stringify(b.map, null, 2))
    files.push('map.json')
    return send(res, 200, { dir, files })
  }

  if (p === '/api/save' && req.method === 'POST') {
    const b = await body(req)
    const id = safeId(b.id)
    const dir = path.join(WORK, id)
    fs.mkdirSync(dir, { recursive: true })
    fs.writeFileSync(path.join(dir, 'scene.png'), Buffer.from(stripDataURL(b.image), 'base64'))
    return send(res, 200, { url: `/work/${id}/scene.png` })
  }

  // the cut-applied painting alone, staged before any mechanics exist:
  // scene-cut.png is the deliverable, cut.png is the mask so reopening the
  // scene picks the cut back up
  if (p === '/api/savecut' && req.method === 'POST') {
    const b = await body(req)
    if (!b.image) return send(res, 400, { error: 'no image' })
    const id = safeId(b.id)
    const dir = path.join(WORK, id)
    fs.mkdirSync(dir, { recursive: true })
    const files = []
    fs.writeFileSync(path.join(dir, 'scene-cut.png'), Buffer.from(stripDataURL(b.image), 'base64'))
    files.push('scene-cut.png')
    if (b.cut) {
      fs.writeFileSync(path.join(dir, 'cut.png'), Buffer.from(stripDataURL(b.cut), 'base64'))
      files.push('cut.png')
    }
    return send(res, 200, { dir, files })
  }

  return notFound(res)
}

function serveWork(res, rel) {
  const f = path.join(WORK, rel.split('/').map(decodeURIComponent).join(path.sep))
  if (!f.startsWith(WORK) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) return notFound(res)
  res.setHeader('Content-Type', MIME[path.extname(f).toLowerCase()] || 'application/octet-stream')
  res.setHeader('Cache-Control', 'no-store')
  res.end(fs.readFileSync(f))
}

function run(cmd, args) {
  return new Promise((resolve) => {
    const ps = spawn(cmd, args, { windowsHide: true })
    let out = ''
    let err = ''
    ps.stdout.on('data', (d) => (out += d))
    ps.stderr.on('data', (d) => (err += d))
    ps.on('error', (e) => resolve({ code: -1, out, err: err + String(e) }))
    ps.on('close', (code) => resolve({ code, out, err }))
  })
}

function body(req) {
  return new Promise((resolve, reject) => {
    let n = 0
    const chunks = []
    req.on('data', (c) => {
      n += c.length
      if (n > 96 * 1024 * 1024) return reject(new Error('body too big'))
      chunks.push(c)
    })
    req.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'))
      } catch (e) {
        reject(e)
      }
    })
    req.on('error', reject)
  })
}

const stripDataURL = (s) => String(s).replace(/^data:[^,]+,/, '')
const safeId = (s) => (String(s || 'untitled').replace(/[^a-z0-9._-]+/gi, '-') || 'untitled').slice(0, 60)

function send(res, code, obj) {
  const b = Buffer.from(JSON.stringify(obj))
  res.statusCode = code
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Content-Length', b.length)
  res.end(b)
}
function notFound(res) {
  send(res, 404, { error: 'not found' })
}
