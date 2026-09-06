import { Suspense, useMemo, useRef, useState, useEffect } from 'react'
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
import { exportUrl } from '../api.js'

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

function Model({ url, onFaceClick, selectedFace, showGrid, wireframe }) {
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

  const handlePointerDown = (event) => {
    event.stopPropagation()
    if (!meshRef.current || !geometry) return

    raycaster.setFromCamera(pointer, camera)
    const intersects = raycaster.intersectObject(meshRef.current)
    if (intersects.length === 0) return

    const hit = intersects[0]
    const faceIndex = hit.faceIndex ?? 0
    const faceNormal = hit.face?.normal?.clone()?.transformDirection(meshRef.current.matrixWorld)?.toArray() ?? [0, 0, 1]
    const point = hit.point?.toArray() ?? [0, 0, 0]

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
      v0.applyMatrix4(meshRef.current.matrixWorld)
      v1.applyMatrix4(meshRef.current.matrixWorld)
      v2.applyMatrix4(meshRef.current.matrixWorld)
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
  )
}

export default function STLViewer({ url, onFaceClick, selectedFace, guessResult, designId }) {
  const [hint, setHint] = useState(null)
  const [showGrid, setShowGrid] = useState(true)
  const [wireframe, setWireframe] = useState(false)
  const [resetNonce, setResetNonce] = useState(0)
  const prevUrlRef = useRef(url)

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
        <div className="kp-flex kp-gap-2">
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
        </div>
      </div>

      {hint && <div className="kp-viewer-hint">{hint}</div>}
      <div className="kp-viewer-caption">Click a face to guess its parameter · drag to rotate · scroll to zoom</div>
      <Canvas shadows camera={{ position: [100, 100, 100], fov: 50 }} style={{ background: 'var(--kp-background)' }}>
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
            />
            <CameraReset nonce={resetNonce} />
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
