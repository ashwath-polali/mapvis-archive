/* Calls to the local node side. Nothing here knows a key. */

async function jpost<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || r.statusText)
  return j as T
}

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url)
  const j = await r.json()
  if (!r.ok || j.error) throw new Error(j.error || r.statusText)
  return j as T
}

export const balance = () => jget<{ usd?: number }>('/api/balance')

export const generate = (prompt: string, n: number, w: number, h: number) =>
  jpost<{ jobs: { id?: string; seed?: number; error?: string }[] }>('/api/generate', { prompt, n, w, h })

export const jobState = (id: string) =>
  jget<{ state: 'running' | 'done' | 'failed'; images?: string[]; error?: string }>('/api/job/' + encodeURIComponent(id))

export const propose = (image: string) =>
  jpost<{ levels: string; note: Record<string, unknown> }>('/api/propose', { image })

export const saveScene = (id: string, image: string) => jpost<{ url: string }>('/api/save', { id, image })

export interface SavedScene {
  map?: { spawn?: [number, number]; occluders?: { id: number; baseline: number }[] } | null
  levels?: string | null
  occluders?: string | null
  cut?: string | null
}
export const savedScene = (id: string) => jget<SavedScene>('/api/scene/' + encodeURIComponent(id))

// the cut-applied painting on its own, so a map can be cut and staged before
// any mechanics are drawn. Writes scene-cut.png, and cut.png so it reopens.
export const saveCutPNG = (id: string, image: string, cut: string) =>
  jpost<{ dir: string; files: string[] }>('/api/savecut', { id, image, cut })

export const exportBundle = (b: unknown) => jpost<{ dir: string; files: string[] }>('/api/export', b)
