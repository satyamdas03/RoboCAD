import { Suspense, useMemo, useRef, useState, useEffect, useCallback } from 'react'
import { Canvas, useThree, useLoader } from '@react-three/fiber'
import {
  Bounds,
  ContactShadows,
  Grid,
  OrbitControls,
  useBounds,
} from '@react-three/drei'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader'
import * as THREE from 'three'
import { exportUrl, critiqueRender } from '../api.js'

function HighlightedFace({ geometry, faceIndex, color = '#00e5ff' }) {
  const meshRef = useRef()
  const prevGeomRef = useRef(null)

  const highlightGeom = useMemo(() => {
    if (faceIndex == null || !geometry || !geometry.index) return null
    const triGeom = new THREE.BufferGeometry()
    const posAttr = geometry.getAttribute('position')
    const indices = geometry.index.array
    const i0 = indices[faceIndex * 3]
    const i1 = indices[faceIndex * 3 + 1]
    const i2 = indices[faceIndex * 3 + 2]

    const verts = new Float32Array([
      posAttr.getX(i0), posAttr.getY(i0), posAttr.getZ(i0),
      posAttr.getX(i1), posAttr.getY(i1), posAttr.getZ(i1),
      posAttr.getX(i2), posAttr.getY(i2), posAttr.getZ(i2),
    ])
    triGeom.setAttribute('position', new THREE.BufferAttribute(verts, 3))
    triGeom.computeVertexNormals()
    return triGeom
  }, [geometry, faceIndex])

  useEffect(() => {
    if (prevGeomRef.current && prevGeomRef.current !== highlightGeom) {
      prevGeomRef.current.dispose()
    }
    prevGeomRef.current = highlightGeom
    return () => {
      if (prevGeomRef.current) {
        prevGeomRef.current.dispose()
        prevGeomRef.current = null
      }
    }
  }, [highlightGeom])

  if (!highlightGeom) return null

  return (
    <mesh ref={meshRef} geometry={highlightGeom}>
      <meshBasicMaterial color={color} transparent opacity={0.35} side={THREE.DoubleSide} depthTest={false} />
      <lineSegments geometry={highlightGeom}>
        <lineBasicMaterial color={color} transparent opacity={0.9} />
      </lineSegments>
    </mesh>
  )
}

function SceneGrid({ visible }) {
  if (!visible) return null
  return (
    <Grid
      position={[0, -0.01, 0]}
      args={[200, 200]}
      cellSize={10}
      cellThickness={0.5}
      cellColor="rgba(132,147,150,0.25)"
      sectionSize={50}
      sectionThickness={0.8}
      sectionColor="rgba(132,147,150,0.35)"
      fadeDistance={250}
      infiniteGrid
    />
  )
}

function CameraReset({ nonce }) {
  const bounds = useBounds()
  useEffect(() => {
    bounds.refresh().clip().fit()
  }, [nonce, bounds])
  return null
}

function CaptureBridge({ onGlReady }) {
  const gl = useThree((state) => state.gl)
  useEffect(() => {
    onGlReady(gl)
    return () => {}
  }, [gl, onGlReady])
  return null
}

function heatmapColor(t) {
  // t in [0, 1]: blue -> cyan -> green -> yellow -> red
  const stops = [
    [0.0, 0.0, 0.0, 1.0],
    [0.25, 0.0, 0.8, 1.0],
    [0.5, 0.0, 1.0, 0.2],
    [0.75, 1.0, 0.8, 0.0],
    [1.0, 1.0, 0.0, 0.0],
  ]
  let i = 0
  while (i < stops.length - 2 && t > stops[i + 1][0]) {
    i++
  }
  const a = stops[i]
  const b = stops[i + 1]
  const local = Math.max(0, Math.min(1, (t - a[0]) / (b[0] - a[0] + 1e-9)))
  return [
    a[1] + (b[1] - a[1]) * local,
    a[2] + (b[2] - a[2]) * local,
    a[3] + (b[3] - a[3]) * local,
  ]
}

function buildSpatialGrid(nodes, scalars, fallbackMin) {
  const entries = []
  let minX = Infinity, minY = Infinity, minZ = Infinity
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i]
    const s = scalars[i] ?? fallbackMin
    entries.push({ x: n[0], y: n[1], z: n[2], s })
    if (n[0] < minX) minX = n[0]
    if (n[1] < minY) minY = n[1]
    if (n[2] < minZ) minZ = n[2]
    if (n[0] > maxX) maxX = n[0]
    if (n[1] > maxY) maxY = n[1]
    if (n[2] > maxZ) maxZ = n[2]
  }
  const spanX = maxX - minX || 1
  const spanY = maxY - minY || 1
  const spanZ = maxZ - minZ || 1
  // Choose a cell size that gives roughly one node per cell on average.
  const volume = spanX * spanY * spanZ
  const cellSize = Math.max(1e-6, Math.pow(volume / Math.max(1, entries.length), 1 / 3))
  const invCellSize = 1 / cellSize
  const cells = new Map()
  for (const e of entries) {
    const cx = Math.floor((e.x - minX) * invCellSize)
    const cy = Math.floor((e.y - minY) * invCellSize)
    const cz = Math.floor((e.z - minZ) * invCellSize)
    const key = `${cx},${cy},${cz}`
    let list = cells.get(key)
    if (!list) {
      list = []
      cells.set(key, list)
    }
    list.push(e)
  }
  return { cells, cellSize, invCellSize, minX, minY, minZ, fallbackMin, entries }
}

function nearestScalar(grid, x, y, z) {
  if (grid.entries.length === 0) return grid.fallbackMin
  const cx = Math.floor((x - grid.minX) * grid.invCellSize)
  const cy = Math.floor((y - grid.minY) * grid.invCellSize)
  const cz = Math.floor((z - grid.minZ) * grid.invCellSize)
  let bestDist = Infinity
  let bestS = grid.fallbackMin
  // Search the 3x3x3 neighborhood of cells; this is sufficient because the
  // chosen cell size guarantees the nearest neighbor lies in an adjacent cell.
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      for (let dz = -1; dz <= 1; dz++) {
        const key = `${cx + dx},${cy + dy},${cz + dz}`
        const list = grid.cells.get(key)
        if (!list) continue
        for (const n of list) {
          const ddx = x - n.x
          const ddy = y - n.y
          const ddz = z - n.z
          const d = ddx * ddx + ddy * ddy + ddz * ddz
          if (d < bestDist) {
            bestDist = d
            bestS = n.s
          }
        }
      }
    }
  }
  // Defensive fallback: if the query point sits outside the grid's bounding
  // box, the nearest node may be in a non-adjacent cell; scan all entries.
  if (bestDist === Infinity) {
    for (const n of grid.entries) {
      const ddx = x - n.x
      const ddy = y - n.y
      const ddz = z - n.z
      const d = ddx * ddx + ddy * ddy + ddz * ddz
      if (d < bestDist) {
        bestDist = d
        bestS = n.s
      }
    }
  }
  return bestS
}

function applyScalarField(geometry, scalarField, materialRef) {
  if (!geometry || !scalarField || !scalarField.nodes?.length || !scalarField.scalars?.length) {
    clearScalarField(geometry, materialRef)
    return
  }
  const nodes = scalarField.nodes
  const scalars = scalarField.scalars
  const min = scalarField.min ?? Math.min(...scalars)
  const max = scalarField.max ?? Math.max(...scalars)
  const range = max - min || 1e-9

  const posAttr = geometry.getAttribute('position')
  const count = posAttr.count
  const colors = new Float32Array(count * 3)
  const grid = buildSpatialGrid(nodes, scalars, min)

  for (let i = 0; i < count; i++) {
    const bestS = nearestScalar(grid, posAttr.getX(i), posAttr.getY(i), posAttr.getZ(i))
    const t = Math.max(0, Math.min(1, (bestS - min) / range))
    const [r, g, b] = heatmapColor(t)
    colors[i * 3] = r
    colors[i * 3 + 1] = g
    colors[i * 3 + 2] = b
  }

  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  if (materialRef.current) {
    materialRef.current.vertexColors = true
    materialRef.current.needsUpdate = true
  }
}

function clearScalarField(geometry, materialRef) {
  if (!geometry) return
  const colorAttr = geometry.getAttribute('color')
  if (colorAttr) {
    geometry.deleteAttribute('color')
  }
  if (materialRef.current) {
    materialRef.current.vertexColors = false
    materialRef.current.needsUpdate = true
  }
}

function Model({ url, onFaceClick, selectedFace, showGrid, wireframe, scalarField }) {
  const meshRef = useRef()
  const geometry = useLoader(STLLoader, exportUrl(url))
  const { camera, raycaster, pointer } = useThree()
  const materialRef = useRef(null)
  const bounds = useBounds()

  useEffect(() => {
    if (geometry && geometry.boundingBox) {
      bounds.refresh().clip().fit()
    }
    return () => {
      if (geometry && geometry.dispose) {
        geometry.dispose()
      }
      if (materialRef.current) {
        materialRef.current.dispose()
      }
    }
  }, [geometry, bounds])

  useEffect(() => {
    if (!geometry) return
    if (scalarField) {
      applyScalarField(geometry, scalarField, materialRef)
    } else {
      clearScalarField(geometry, materialRef)
    }
  }, [geometry, scalarField])

  const handlePointerDown = (event) => {
    event.stopPropagation()
    if (!meshRef.current || !geometry) return

    raycaster.setFromCamera(pointer, camera)
    const intersects = raycaster.intersectObject(meshRef.current)
    if (intersects.length === 0) return

    const hit = intersects[0]
    const faceIndex = hit.faceIndex ?? 0
    // Report the face in CAD (mesh-local, Z-up) coordinates: the model group is
    // rotated for display, but the backend reasons about the part as modelled.
    const faceNormal = hit.face?.normal?.clone()?.toArray() ?? [0, 0, 1]
    const point = hit.point ? meshRef.current.worldToLocal(hit.point.clone()).toArray() : [0, 0, 0]

    const posAttr = geometry.getAttribute('position')
    const indices = geometry.index?.array
    let centroid = point
    if (indices) {
      const i0 = indices[faceIndex * 3]
      const i1 = indices[faceIndex * 3 + 1]
      const i2 = indices[faceIndex * 3 + 2]
      const v0 = new THREE.Vector3(posAttr.getX(i0), posAttr.getY(i0), posAttr.getZ(i0))
      const v1 = new THREE.Vector3(posAttr.getX(i1), posAttr.getY(i1), posAttr.getZ(i1))
      const v2 = new THREE.Vector3(posAttr.getX(i2), posAttr.getY(i2), posAttr.getZ(i2))
      centroid = [
        (v0.x + v1.x + v2.x) / 3,
        (v0.y + v1.y + v2.y) / 3,
        (v0.z + v1.z + v2.z) / 3,
      ]
    }

    onFaceClick({ faceIndex, faceNormal, centroid })
  }

  return (
    <group>
      <SceneGrid visible={showGrid} />
      {/* CAD models are Z-up; three.js is Y-up. Rotate so parts stand on the grid. */}
      <group rotation={[-Math.PI / 2, 0, 0]}>
      <mesh
        ref={meshRef}
        geometry={geometry}
        castShadow
        receiveShadow
        onPointerDown={handlePointerDown}
      >
        <meshStandardMaterial
          ref={materialRef}
          color="#d8dce5"
          roughness={0.45}
          metalness={0.25}
        />
      </mesh>
      {wireframe && (
        <mesh geometry={geometry}>
          <meshBasicMaterial color="#1a202c" wireframe transparent opacity={0.25} />
        </mesh>
      )}
      <HighlightedFace geometry={geometry} faceIndex={selectedFace} />
      </group>
    </group>
  )
}

export default function STLViewer({ url, onFaceClick, selectedFace, guessResult, designId, scalarField }) {
  const [hint, setHint] = useState(null)
  const [showGrid, setShowGrid] = useState(true)
  const [wireframe, setWireframe] = useState(false)
  const [resetNonce, setResetNonce] = useState(0)
  const [critique, setCritique] = useState(null)
  const [critiqueLoading, setCritiqueLoading] = useState(false)
  const [critiqueError, setCritiqueError] = useState(null)
  const glRef = useRef(null)
  const prevUrlRef = useRef(url)

  const handleGlReady = useCallback((gl) => {
    glRef.current = gl
  }, [])

  useEffect(() => {
    if (guessResult?.guessed_parameter) {
      const axisLabels = ['X', 'Y', 'Z']
      const axisLabel = axisLabels[guessResult.axis] ?? guessResult.axis
      setHint(
        `Selected ${axisLabel}-facing face → parameter "${guessResult.guessed_parameter}" (${guessResult.suggested_value}${guessResult.unit || 'mm'})`
      )
      const timer = setTimeout(() => setHint(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [guessResult])

  // Invalidate the global THREE/useLoader cache for the previous design URL so
  // switching designs repeatedly does not grow GPU/JS heap.
  useEffect(() => {
    const prevUrl = prevUrlRef.current
    if (prevUrl && prevUrl !== url) {
      const key = exportUrl(prevUrl)
      if (THREE.Cache.get(key) !== undefined) {
        THREE.Cache.remove(key)
      }
    }
    prevUrlRef.current = url
  }, [url])

  async function runCritique() {
    if (!designId || !glRef.current?.domElement) return
    setCritiqueLoading(true)
    setCritiqueError(null)
    try {
      const dataUrl = glRef.current.domElement.toDataURL('image/png')
      const blob = await (await fetch(dataUrl)).blob()
      const result = await critiqueRender(designId, blob)
      setCritique(result.critique)
    } catch (err) {
      setCritiqueError(err.message || 'Render critique failed')
    } finally {
      setCritiqueLoading(false)
    }
  }

  if (!url) {
    return (
      <section className="kp-viewer" aria-label="3D model viewer">
        <div className="kp-viewer-overlay">
          <span className="kp-mono kp-text-subtle" style={{ fontSize: '0.75rem' }}>
            {designId ? `Design #${designId.slice(0, 8)}` : 'No model'}
          </span>
        </div>
        <div className="kp-viewer-placeholder">
          <div className="kp-empty-icon" aria-hidden="true">◈</div>
          <p>Generated model will appear here.</p>
          <p className="kp-small kp-text-muted">Type a prompt and click Generate to preview the part.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="kp-viewer" aria-label="3D model viewer">
      <div className="kp-viewer-overlay">
        <span className="kp-mono kp-text-subtle" style={{ fontSize: '0.75rem' }}>
          {designId ? `Design #${designId.slice(0, 8)}` : 'Generated model'}
        </span>
        <div className="kp-flex kp-gap-2 kp-flex-wrap">
          <button
            type="button"
            className="kp-button kp-button-small kp-button-ghost"
            title="Reset camera to fit model"
            onClick={() => setResetNonce((n) => n + 1)}
          >
            Reset
          </button>
          <button
            type="button"
            className={`kp-button kp-button-small ${showGrid ? 'kp-button-ghost' : 'kp-button-secondary'}`}
            title="Toggle ground grid"
            onClick={() => setShowGrid((v) => !v)}
          >
            Grid
          </button>
          <button
            type="button"
            className={`kp-button kp-button-small ${wireframe ? 'kp-button-secondary' : 'kp-button-ghost'}`}
            title="Toggle wireframe overlay"
            onClick={() => setWireframe((v) => !v)}
          >
            Wire
          </button>
          <button
            type="button"
            className="kp-button kp-button-small kp-button-primary"
            title="Run NVIDIA AI render critique"
            onClick={runCritique}
            disabled={critiqueLoading || !designId}
          >
            {critiqueLoading ? '…' : 'AI Critique'}
          </button>
        </div>
      </div>

      {hint && <div className="kp-viewer-hint">{hint}</div>}
      {critiqueError && <div className="kp-viewer-hint kp-alert kp-alert-error">{critiqueError}</div>}
      {critique && (
        <div className="kp-viewer-hint" style={{ maxWidth: '24rem' }}>
          <div className="kp-flex kp-gap-2 kp-align-center" style={{ marginBottom: '0.25rem' }}>
            <span className={`kp-badge ${critique.score >= 80 ? 'kp-badge-success' : critique.score >= 50 ? 'kp-badge-warning' : 'kp-badge-error'}`}>
              Score: {critique.score ?? '—'}
            </span>
            {!critique.safe_to_show_user && (
              <span className="kp-badge kp-badge-error">Not safe to show</span>
            )}
          </div>
          {critique.issues?.length > 0 && (
            <ul className="kp-small" style={{ margin: '0.25rem 0', paddingLeft: '1rem' }}>
              {critique.issues.map((issue, idx) => (
                <li key={idx}>
                  <strong>{issue.severity}</strong> ({issue.category}): {issue.message}
                </li>
              ))}
            </ul>
          )}
          {critique.suggestions?.length > 0 && (
            <div className="kp-small kp-text-subtle">
              Suggestions: {critique.suggestions.join(' · ')}
            </div>
          )}
          <button
            type="button"
            className="kp-button kp-button-small kp-button-ghost"
            style={{ marginTop: '0.25rem' }}
            onClick={() => setCritique(null)}
          >
            Dismiss
          </button>
        </div>
      )}
      <div className="kp-viewer-caption">Click a face to guess its parameter · drag to rotate · scroll to zoom</div>
      <Canvas
        shadows
        gl={{ preserveDrawingBuffer: true }}
        camera={{ position: [100, 100, 100], fov: 50 }}
        style={{ background: 'var(--kp-background)' }}
      >
        <hemisphereLight intensity={0.6} groundColor="#1a202c" color="#e8eef2" />
        <directionalLight position={[80, 120, 60]} intensity={1.4} castShadow shadow-mapSize={[2048, 2048]} shadow-bias={-0.0001} />
        <directionalLight position={[-60, -40, -40]} intensity={0.35} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.2} maxDuration={0.4}>
            <Model
              url={url}
              onFaceClick={onFaceClick}
              selectedFace={selectedFace}
              showGrid={showGrid}
              wireframe={wireframe}
              scalarField={scalarField}
            />
            <CameraReset nonce={resetNonce} />
            <CaptureBridge onGlReady={handleGlReady} />
          </Bounds>
        </Suspense>
        <ContactShadows
          key={url}
          position={[0, -0.01, 0]}
          opacity={0.35}
          scale={200}
          blur={2}
          far={250}
          frames={1}
        />
        <OrbitControls makeDefault />
      </Canvas>
    </section>
  )
}
