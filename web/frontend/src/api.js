const API_BASE = import.meta.env.VITE_API_BASE || ''

async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }
  return response.json()
}

export async function checkHealth() {
  return apiFetch('/health')
}

export async function generateDesign({ prompt, max_retries = 2, model = null }) {
  return apiFetch('/generate', {
    method: 'POST',
    body: JSON.stringify({ prompt, max_retries, model }),
  })
}

export async function listDesigns() {
  return apiFetch('/designs')
}

export async function loadDesign(id) {
  return apiFetch(`/designs/${id}`)
}

export async function regenerateDesign(id, parameterUpdates) {
  return apiFetch(`/designs/${id}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ parameter_updates: parameterUpdates }),
  })
}

export async function updateDesignTags(id, tags) {
  return apiFetch(`/designs/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ tags }),
  })
}

export async function remixDesign(id, { prompt, max_retries = 2, model = null }) {
  return apiFetch(`/designs/${id}/remix`, {
    method: 'POST',
    body: JSON.stringify({ prompt, max_retries, model }),
  })
}

export async function guessParameter(id, { faceNormal, faceCentroid }) {
  return apiFetch(`/designs/${id}/guess-parameter`, {
    method: 'POST',
    body: JSON.stringify({ face_normal: faceNormal, face_centroid: faceCentroid }),
  })
}

export function exportUrl(path) {
  return `${API_BASE}${path}`
}
