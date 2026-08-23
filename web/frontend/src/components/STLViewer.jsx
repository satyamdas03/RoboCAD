import { Suspense, useMemo, useRef, useState, useEffect } from 'react'
import { Canvas, useThree, useLoader } from '@react-three/fiber'
import { OrbitControls, Center } from '@react-three/drei'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader'
import * as THREE from 'three'
import { exportUrl } from '../api.js'

function HighlightedFace({ geometry, faceIndex, color = '#0d9488' }) {
  const meshRef = useRef()
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

  if (!highlightGeom) return null

  return (
    <mesh ref={meshRef} geometry={highlightGeom}>
      <meshBasicMaterial color={color} transparent opacity={0.55} side={THREE.DoubleSide} depthTest={false} />
    </mesh>
  )
}

function Model({ url, onFaceClick, selectedFace }) {
  const meshRef = useRef()
  const geometry = useLoader(STLLoader, exportUrl(url))
  const { camera, raycaster, pointer } = useThree()

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
      <mesh
        ref={meshRef}
        geometry={geometry}
        castShadow
        receiveShadow
        onPointerDown={handlePointerDown}
      >
        <meshStandardMaterial color="#94a3b8" roughness={0.45} metalness={0.15} />
      </mesh>
      <HighlightedFace geometry={geometry} faceIndex={selectedFace} />
    </group>
  )
}

export default function STLViewer({ url, onFaceClick, selectedFace, guessResult }) {
  const [hint, setHint] = useState(null)

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

  if (!url) {
    return (
      <section className="rc-viewer" aria-label="3D model viewer">
        <div className="rc-viewer-placeholder">
          <div className="rc-empty-icon" aria-hidden="true">◈</div>
          <p>No model loaded yet. Generate a part to preview it here.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="rc-viewer" aria-label="3D model viewer">
      {hint && <div className="rc-viewer-hint">{hint}</div>}
      <div className="rc-viewer-caption">Click a face to guess its parameter · drag to rotate · scroll to zoom</div>
      <Canvas shadows camera={{ position: [100, 100, 100], fov: 50 }}>
        <ambientLight intensity={0.55} />
        <directionalLight position={[50, 100, 50]} intensity={1.1} castShadow />
        <directionalLight position={[-50, -50, -30]} intensity={0.35} />
        <Suspense fallback={null}>
          <Center>
            <Model url={url} onFaceClick={onFaceClick} selectedFace={selectedFace} />
          </Center>
        </Suspense>
        <OrbitControls makeDefault />
      </Canvas>
    </section>
  )
}
