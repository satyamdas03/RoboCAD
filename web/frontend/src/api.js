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

export function exportUrl(path) {
  return `${API_BASE}${path}`
}
