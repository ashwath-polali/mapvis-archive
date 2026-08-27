/* PixelLab, server side only. The token never leaves this process.
 *
 * It is read the same way scripts/pxl.py reads it: from the MCP server entry in
 * the local tool config, or from PIXELLAB_TOKEN if that is set.
 *
 * Endpoints in use:
 *   POST /v2/generate-image-v2      -> { background_job_id }
 *   GET  /v2/background-jobs/{id}   -> { status, ...images somewhere inside }
 *   GET  /v1/balance                -> { usd }
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const BASE = 'https://api.pixellab.ai'
let cached = null

export function token() {
  if (cached) return cached
  if (process.env.PIXELLAB_TOKEN) return (cached = process.env.PIXELLAB_TOKEN)
  const p = path.join(os.homedir(), '.pixellab.json')
  const d = JSON.parse(fs.readFileSync(p, 'utf8'))
  for (const proj of Object.values(d.projects || {})) {
    const s = (proj.mcpServers || {}).pixellab
    if (!s) continue
    for (const [k, v] of Object.entries(s.headers || {})) {
      if (k.toLowerCase() === 'authorization') return (cached = String(v).split(/\s+/).pop())
    }
    if (s.token) return (cached = s.token)
    if ((s.url || '').includes('token=')) return (cached = s.url.split('token=')[1].split('&')[0])
  }
  throw new Error('set PIXELLAB_TOKEN to your api key')
}

async function call(method, route, body) {
  const r = await fetch(BASE + route, {
    method,
    headers: {
      Authorization: 'Bearer ' + token(),
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await r.text()
  if (!r.ok) throw new Error(`pixellab ${r.status} ${text.slice(0, 300)}`)
  return text ? JSON.parse(text) : {}
}

export const balance = () => call('GET', '/v1/balance')

export async function submit({ prompt, w, h, seed, styleImage }) {
  const body = {
    description: prompt,
    image_size: { width: w, height: h },
    no_background: false,
  }
  if (seed != null) body.seed = seed
  if (styleImage) {
    body.style_image = { image: { type: 'base64', base64: styleImage.base64 }, size: { width: styleImage.w, height: styleImage.h } }
    body.style_options = { color_palette: true, outline: true, detail: true, shading: true }
  }
  const out = await call('POST', '/v2/generate-image-v2', body)
  return out.background_job_id
}

export async function job(id) {
  const j = await call('GET', '/v2/background-jobs/' + encodeURIComponent(id))
  const st = String(j.status || '').toLowerCase()
  if (['completed', 'success', 'succeeded', 'done'].includes(st)) {
    return { state: 'done', images: collect(j) }
  }
  if (['failed', 'error', 'cancelled'].includes(st)) {
    return { state: 'failed', error: (j.error || j.message || st).toString().slice(0, 200) }
  }
  return { state: 'running' }
}

// the image payload sits at a different depth depending on the model, so walk
// the response for anything that looks like a png in base64
function collect(o, acc = [], depth = 0) {
  if (depth > 8) return acc
  if (Array.isArray(o)) {
    for (const v of o) collect(v, acc, depth + 1)
  } else if (o && typeof o === 'object') {
    const b = o.base64
    if (typeof b === 'string' && b.length > 500) acc.push(b)
    else for (const v of Object.values(o)) collect(v, acc, depth + 1)
  }
  return acc
}
