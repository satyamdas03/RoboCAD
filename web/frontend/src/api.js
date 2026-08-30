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

export async function generateDesign({ prompt, max_retries = 2, model = null, detectDomain = false, decompose = true }) {
  return apiFetch('/generate', {
    method: 'POST',
    body: JSON.stringify({ prompt, max_retries, model, detect_domain: detectDomain, decompose }),
  })
}

export async function decomposePrompt(prompt) {
  return apiFetch('/decompose', {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  })
}

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

export async function loadFeatureTree(id) {
  return apiFetch(`/designs/${id}/feature-tree`)
}

export async function loadAssembly(id) {
  return apiFetch(`/designs/${id}/assembly`)
}

export async function regenerateFromFeatureTree(id, parameterUpdates) {
  return apiFetch(`/designs/${id}/regenerate-from-feature-tree`, {
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

export async function getManufacturingReport(id) {
  return apiFetch(`/designs/${id}/manufacturing-report`)
}

export async function getDFMReport(id) {
  return apiFetch(`/designs/${id}/dfm-report`)
}

export async function runFitCheck(id, { otherDesignId, name = 'fit_check', clearanceThresholdMm = 0.05, interferenceThresholdMm = -0.05, samples = 2000 }) {
  return apiFetch(`/designs/${id}/fit-check`, {
    method: 'POST',
    body: JSON.stringify({
      other_design_id: otherDesignId,
      name,
      clearance_threshold_mm: clearanceThresholdMm,
      interference_threshold_mm: interferenceThresholdMm,
      samples,
    }),
  })
}

export async function runFEA(id, { fixedFace = '-x', loadMagnitudeN = 100, material = 'PLA' } = {}) {
  return apiFetch(`/designs/${id}/fea-report`, {
    method: 'POST',
    body: JSON.stringify({ fixed_face: fixedFace, load_magnitude_n: loadMagnitudeN, material }),
  })
}

export async function simulateDesign(id, { material = 'PLA', tolerance = 0.1 } = {}) {
  return apiFetch(`/designs/${id}/simulate`, {
    method: 'POST',
    body: JSON.stringify({ material, tolerance }),
  })
}

export async function getSimulationReport(id) {
  return apiFetch(`/designs/${id}/simulation`)
}

export async function composeScene(id, { template = 'gripper_cube_grasp', material = 'PLA', tolerance = 0.1 } = {}) {
  return apiFetch(`/designs/${id}/scene`, {
    method: 'POST',
    body: JSON.stringify({ template, material, tolerance }),
  })
}

export async function getSceneReport(id, template = 'gripper_cube_grasp') {
  const params = new URLSearchParams()
  params.set('template', template)
  return apiFetch(`/designs/${id}/scene?${params.toString()}`)
}

export async function getCapabilities() {
  return apiFetch('/capabilities')
}

export async function runHandshake(id, template = 'wedge_push_block') {
  const params = new URLSearchParams()
  params.set('template', template)
  return apiFetch(`/designs/${id}/handshake?${params.toString()}`, {
    method: 'POST',
  })
}

export async function getHandshakeReport(id, template = 'wedge_push_block') {
  const params = new URLSearchParams()
  params.set('template', template)
  return apiFetch(`/designs/${id}/handshake?${params.toString()}`)
}

export async function recommendSkill(id, skillDescription = 'push the block to the goal') {
  return apiFetch(`/designs/${id}/recommend-skill`, {
    method: 'POST',
    body: JSON.stringify({ skill_description: skillDescription }),
  })
}

export async function trainSkill(id, { skillDescription = 'push the block to the goal', nIters = 20, popSize = 50, evalEpisodes = 10 } = {}) {
  return apiFetch(`/designs/${id}/train-skill`, {
    method: 'POST',
    body: JSON.stringify({
      skill_description: skillDescription,
      n_iters: nIters,
      pop_size: popSize,
      eval_episodes: evalEpisodes,
    }),
  })
}

export async function getSkills(id) {
  return apiFetch(`/designs/${id}/skills`)
}

export async function runVariantSweep(id, { parameterRanges, nVariants = 5, tolerance = 0.1, runStability = true }) {
  return apiFetch(`/designs/${id}/variant-sweep`, {
    method: 'POST',
    body: JSON.stringify({
      parameter_ranges: parameterRanges,
      n_variants: nVariants,
      tolerance,
      run_stability: runStability,
    }),
  })
}

export async function listOnshapeDocuments(query = '', limit = 20) {
  const params = new URLSearchParams()
  if (query) params.set('q', query)
  params.set('limit', String(limit))
  return apiFetch(`/onshape/documents?${params.toString()}`)
}

export async function uploadToOnshape(id, { documentId, workspaceId, documentName }) {
  return apiFetch(`/designs/${id}/onshape`, {
    method: 'POST',
    body: JSON.stringify({
      document_id: documentId,
      workspace_id: workspaceId,
      document_name: documentName,
    }),
  })
}

export function exportUrl(path) {
  return `${API_BASE}${path}`
}

export function getBundleUrl(id) {
  return `${API_BASE}/designs/${id}/bundle`
}

export async function synthesizeAssembly(id) {
  return apiFetch(`/designs/${id}/synthesize-assembly`, { method: 'POST' })
}

export async function getAssemblyCollision(id) {
  return apiFetch(`/designs/${id}/assembly-collision`)
}

export async function getAssemblyPoses(id, { samplesPerJoint = 8 } = {}) {
  const params = new URLSearchParams()
  params.set('samples_per_joint', String(samplesPerJoint))
  return apiFetch(`/designs/${id}/assembly-poses?${params.toString()}`)
}

export async function runAeroAnalysis(id, { naca = '0012', angleOfAttackDeg = 0.0, flowVelocityMs = 10.0 } = {}) {
  return apiFetch(`/designs/${id}/aero-report`, {
    method: 'POST',
    body: JSON.stringify({ naca, angle_of_attack_deg: angleOfAttackDeg, flow_velocity_ms: flowVelocityMs }),
  })
}

export async function getAeroReport(id) {
  return apiFetch(`/designs/${id}/aero-report`)
}

export async function runThermalAnalysis(id, { heatFluxW = 10.0, ambientTempC = 25.0, convectionCoefficientWPerM2K = 50.0 } = {}) {
  return apiFetch(`/designs/${id}/thermal-report`, {
    method: 'POST',
    body: JSON.stringify({
      heat_flux_w: heatFluxW,
      ambient_temp_c: ambientTempC,
      convection_coefficient_w_per_m2_k: convectionCoefficientWPerM2K,
    }),
  })
}

export async function getThermalReport(id) {
  return apiFetch(`/designs/${id}/thermal-report`)
}

export async function exportCFDMesh(id, { solver = 'su2_stub', angleOfAttackDeg = 0.0, flowVelocityMs = 10.0, characteristicLengthM = 0.1 } = {}) {
  return apiFetch(`/designs/${id}/cfd-mesh`, {
    method: 'POST',
    body: JSON.stringify({
      solver,
      angle_of_attack_deg: angleOfAttackDeg,
      flow_velocity_ms: flowVelocityMs,
      characteristic_length_m: characteristicLengthM,
    }),
  })
}

export async function runElectronicsAnalysis(id) {
  return apiFetch(`/designs/${id}/electronics-report`, { method: 'POST' })
}

export async function getElectronicsReport(id) {
  return apiFetch(`/designs/${id}/electronics-report`)
}

export async function exportIDF(id, { boardName = 'ROBOCAD_PCB' } = {}) {
  return apiFetch(`/designs/${id}/idf-export`, {
    method: 'POST',
    body: JSON.stringify({ board_name: boardName }),
  })
}

export async function runVerification(id, { loadCase = 'static_stress', materials = {}, parameters = {} } = {}) {
  return apiFetch(`/designs/${id}/verify`, {
    method: 'POST',
    body: JSON.stringify({ load_case: loadCase, materials, parameters }),
  })
}

export async function getVerificationReport(id, reportId) {
  return apiFetch(`/designs/${id}/verify-report/${reportId}`)
}

export async function checkMeshQuality(id) {
  return apiFetch(`/designs/${id}/mesh-quality-check`, { method: 'POST' })
}

export async function listRobotTemplates() {
  return apiFetch('/robot-templates')
}

export async function createRobotTemplate({ template, parameters = {} }) {
  return apiFetch('/robot-templates', {
    method: 'POST',
    body: JSON.stringify({ template, parameters }),
  })
}

export async function runRobotAnalysis(id, { payloadKg = 5.0, safetyFactor = 2.0, robotMassKg = 20.0, lateralAccelMS2 = 0.5, endEffectorId = 'hand_r', swingFootId = 'foot_l' } = {}) {
  return apiFetch(`/designs/${id}/robot-analysis`, {
    method: 'POST',
    body: JSON.stringify({
      payload_kg: payloadKg,
      safety_factor: safetyFactor,
      robot_mass_kg: robotMassKg,
      lateral_accel_m_s2: lateralAccelMS2,
      end_effector_id: endEffectorId,
      swing_foot_id: swingFootId,
    }),
  })
}
