import { Suspense, useMemo, useRef, useState, useEffect } from 'react'
import { Canvas, useThree, useLoader } from '@react-three/fiber'
import { OrbitControls, Center } from '@react-three/drei'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader'
import * as THREE from 'three'
import { exportUrl } from '../api.js'

function HighlightedFace({ geometry, faceIndex, color = '#f59e0b' }) {
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
      <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} depthTest={false} />
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

    // Compute centroid of the intersected triangle.
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
        <meshStandardMaterial color="#3b82f6" roughness={0.4} metalness={0.1} />
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
        `Selected ${axisLabel}-facing face -> parameter "${guessResult.guessed_parameter}" (${guessResult.suggested_value}${guessResult.unit || 'mm'})`
      )
      const timer = setTimeout(() => setHint(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [guessResult])

  if (!url) {
    return (
      <div className="viewer-placeholder">
        <p>No model to display yet.</p>
      </div>
    )
  }

  return (
    <div className="viewer" style={{ height: '400px', border: '1px solid #ddd', borderRadius: '4px', position: 'relative' }}>
      {hint && (
        <div
          style={{
            position: 'absolute',
            top: '0.5rem',
            left: '50%',
            transform: 'translateX(-50%)',
            background: '#fef3c7',
            color: '#92400e',
            padding: '0.4rem 0.8rem',
            borderRadius: '4px',
            fontSize: '0.85rem',
            zIndex: 10,
            pointerEvents: 'none',
            border: '1px solid #f59e0b',
          }}
        >
          {hint}
        </div>
      )}
      <div style={{ position: 'absolute', bottom: '0.4rem', left: '0.5rem', color: '#64748b', fontSize: '0.75rem', zIndex: 10, pointerEvents: 'none' }}>
        Click a face to guess its parameter
      </div>
      <Canvas shadows camera={{ position: [100, 100, 100], fov: 50 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[50, 100, 50]} intensity={1} castShadow />
        <Suspense fallback={null}>
          <Center>
            <Model url={url} onFaceClick={onFaceClick} selectedFace={selectedFace} />
          </Center>
        </Suspense>
        <OrbitControls makeDefault />
      </Canvas>
    </div>
  )
}
