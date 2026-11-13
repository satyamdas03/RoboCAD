// Single source of the Labs flag on the frontend.
//
// ROBOCAD_LABS is read at build and dev-server start by vite.config.js and injected as
// __ROBOCAD_LABS__. Every frozen panel (aero, thermal, electronics, morphology, gait, brain,
// HERMES, marketplace, world builder, capability handshake) is mounted only when this is true,
// so "is this in the product" has one answer instead of a per-panel judgement.
//
// The flag defaults off. Absent the injected constant, for example in a bare test runner, it is
// off as well: a frozen feature never appears because a build step was skipped.
export const LABS = (() => {
  try {
    return String(__ROBOCAD_LABS__) === '1'
  } catch {
    return false
  }
})()

export default LABS
