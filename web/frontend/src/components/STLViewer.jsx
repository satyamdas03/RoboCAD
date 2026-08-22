import { Suspense, useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Center } from '@react-three/drei'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader'
import * as THREE from 'three'
import { exportUrl } from '../api.js'

function Model({ url }) {
  const geometry = useMemo(() => {
    const loader = new STLLoader()
    return loader.load(exportUrl(url))
  }, [url])

  return (
    <mesh geometry={geometry} castShadow receiveShadow>
      <meshStandardMaterial color="#3b82f6" roughness={0.4} metalness={0.1} />
    </mesh>
  )
}

export default function STLViewer({ url }) {
  if (!url) {
    return (
      <div className="viewer-placeholder">
        <p>No model to display yet.</p>
      </div>
    )
  }

  return (
    <div className="viewer" style={{ height: '400px', border: '1px solid #ddd', borderRadius: '4px' }}>
      <Canvas shadows camera={{ position: [100, 100, 100], fov: 50 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[50, 100, 50]} intensity={1} castShadow />
        <Suspense fallback={null}>
          <Center>
            <Model url={url} />
          </Center>
        </Suspense>
        <OrbitControls makeDefault />
      </Canvas>
    </div>
  )
}
