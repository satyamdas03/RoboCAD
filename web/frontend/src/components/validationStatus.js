// A merged assembly preview is never one watertight solid, so the backend
// reports manifold/watertight as false for it while validating every body on
// its own. Surface that as a per-body pass instead of a misleading failure.
const PER_BODY_NOTE = /separate watertight bodies/i

export function geometryFlagStatus(validation, flag) {
  if (validation?.[flag]) return { label: 'OK', ok: true }
  const perBody = validation?.valid && (validation.warnings || []).some((w) => PER_BODY_NOTE.test(w))
  if (perBody) return { label: 'OK · per body', ok: true }
  return { label: 'FAIL', ok: false }
}
