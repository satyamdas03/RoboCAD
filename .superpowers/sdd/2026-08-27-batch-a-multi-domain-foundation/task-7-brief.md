> Task 7 brief extracted from `docs/superpowers/plans/2026-08-27-batch-a-multi-domain-foundation.md`

### Task 7: Frontend domain badges and inspector card

**Files:**
- Create: `web/frontend/src/components/DomainBadge.jsx`
- Modify: `web/frontend/src/components/HistorySidebar.jsx`
- Modify: `web/frontend/src/App.jsx`
- Modify: `web/frontend/src/api.js`

**Interfaces:**
- Consumes: `GET /designs` summary now includes `domain`
- Produces: `DomainBadge` component, `loadDomainIntent` API helper

- [ ] **Step 1: Add API helper**

In `web/frontend/src/api.js`, add:

```javascript
export async function classifyDomain(prompt) {
  const resp = await fetch(`${API_BASE}/classify-domain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!resp.ok) throw new Error('domain classification failed')
  return resp.json()
}

export async function loadDomainIntent(id) {
  const resp = await fetch(`${API_BASE}/designs/${id}/domain-intent`)
  if (resp.status === 404) return null
  if (!resp.ok) throw new Error('failed to load domain intent')
  return resp.json()
}
```

- [ ] **Step 2: Create DomainBadge component**

In `web/frontend/src/components/DomainBadge.jsx`:

```jsx
const DOMAIN_COLORS = {
  mechanical: '#00e5ff',
  aero: '#76ff03',
  thermal: '#ff9100',
  electronics: '#d500f9',
  humanoid: '#ff4081',
  multi: '#ffd600',
}

export default function DomainBadge({ domain, multi }) {
  const color = DOMAIN_COLORS[multi ? 'multi' : domain] || '#ffffff'
  const label = multi ? 'multi-domain' : domain
  return (
    <span style={{ color, border: `1px solid ${color}`, borderRadius: 4, padding: '2px 6px', fontSize: 11, textTransform: 'uppercase' }}>
      {label}
    </span>
  )
}
```

- [ ] **Step 3: Show badge in history sidebar**

In `web/frontend/src/components/HistorySidebar.jsx`, import `DomainBadge` and render it next to each design item if `item.domain` exists.

- [ ] **Step 4: Add domain-intent inspector card in App.jsx**

In `web/frontend/src/App.jsx`:
- Add state `domainIntent`.
- In `handleGenerate`, after generation, call `classifyDomain` and store result if `detect_domain` enabled.
- In `handleSelect`, call `loadDomainIntent` and store it.
- Render a small inspector card (reuse existing right-panel style) showing `domainIntent.domain`, parameters, and notes.

- [ ] **Step 5: Verify frontend build**

Run:

```bash
cd web/frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/DomainBadge.jsx web/frontend/src/components/HistorySidebar.jsx web/frontend/src/App.jsx web/frontend/src/api.js
git commit -m "feat(ui): domain badges, classify API, and domain-intent inspector card"
```

**Report file:** `.superpowers/sdd/2026-08-27-batch-a-multi-domain-foundation/task-7-report.md`

Write the report there and return only: status, commits, test summary, and any concerns.
