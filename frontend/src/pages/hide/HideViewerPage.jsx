import { useCallback, useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import ServerScanPicker from '../../components/hide/ServerScanPicker.jsx'
import { CubeIcon } from '../../components/icons.jsx'
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Spinner } from '../../components/ui/index.js'
import { cn } from '../../lib/cn.js'
import { formatBytes } from '../../lib/format.js'
import {
  SUPPORTED_EXTENSIONS,
  basenameOf,
  classifyAssetFiles,
  disposeThreeObject,
  extractMeshTelemetry,
  inspectObjText,
  matchMtlTextures,
  parseMtlTextureReferences,
} from '../../lib/hideAssets.js'

const SHADING_MODES = [
  ['textured', 'Textured'],
  ['clay', 'Clay'],
  ['wireframe', 'Wireframe'],
  ['overlay', 'Surface + Wire'],
]

const CAMERA_PRESETS = [
  ['iso', 'Reset'],
  ['front', 'Front'],
  ['left', 'Left'],
  ['right', 'Right'],
  ['top', 'Top'],
]

function setMaterialsAppearance(root, { shadingMode, doubleSided, clayMaterial, originalMaterials, wireOverlays }) {
  if (!root) return
  const side = doubleSided ? THREE.DoubleSide : THREE.FrontSide

  // Remove previous wireframe overlay children first.
  for (const overlay of wireOverlays) {
    if (overlay.parent) overlay.parent.remove(overlay)
    overlay.geometry?.dispose?.()
    overlay.material?.dispose?.()
  }
  wireOverlays.length = 0

  root.traverse((child) => {
    if (!child.isMesh) return
    const orig = originalMaterials.get(child.uuid)
    if (!orig) return

    if (shadingMode === 'clay') {
      clayMaterial.side = side
      clayMaterial.wireframe = false
      child.material = clayMaterial
      return
    }

    child.material = orig
    const mats = Array.isArray(orig) ? orig : [orig]
    for (const m of mats) {
      m.side = side
      m.wireframe = shadingMode === 'wireframe'
      m.needsUpdate = true
    }

    if (shadingMode === 'overlay' && child.geometry) {
      const wireMat = new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        wireframe: true,
        transparent: true,
        opacity: 0.28,
        depthTest: true,
      })
      const wireMesh = new THREE.Mesh(child.geometry.clone(), wireMat)
      wireMesh.name = '__wireframe_overlay__'
      wireMesh.raycast = () => {}
      child.add(wireMesh)
      wireOverlays.push(wireMesh)
    }
  })
}

export default function HideViewerPage() {
  const mountRef = useRef(null)
  const sceneRef = useRef(null)
  const rendererRef = useRef(null)
  const cameraRef = useRef(null)
  const controlsRef = useRef(null)
  const helpersRef = useRef({ grid: null, axes: null })
  const lightsRef = useRef({ ambient: null, key: null, fill: null })
  const modelRef = useRef(null)
  const originalMaterialsRef = useRef(new Map())
  const wireOverlaysRef = useRef([])
  const clayMaterialRef = useRef(null)

  const [files, setFiles] = useState({ obj: null, mtl: null, textures: [] })
  const [dragging, setDragging] = useState(false)
  const [loadingState, setLoadingState] = useState({ active: false, percent: 0, stage: '' })
  const [stats, setStats] = useState(null)
  const [notices, setNotices] = useState([])
  const [error, setError] = useState(null)
  const [webglError, setWebglError] = useState(null)

  // Visualization controls
  const [shadingMode, setShadingMode] = useState('textured')
  const [doubleSided, setDoubleSided] = useState(true)
  const [showHelpers, setShowHelpers] = useState(true)
  const [autoRotate, setAutoRotate] = useState(false)
  const [lightIntensity, setLightIntensity] = useState(1.0)

  const moveCameraPreset = useCallback((preset) => {
    const camera = cameraRef.current
    const controls = controlsRef.current
    if (!camera || !controls) return
    const dist = 3.1
    const positions = {
      iso: [2.1, 1.35, 2.3],
      front: [0, 0.25, dist],
      left: [-dist, 0.25, 0],
      right: [dist, 0.25, 0],
      top: [0, dist * 1.05, 0.01],
    }
    const [x, y, z] = positions[preset] || positions.iso
    camera.position.set(x, y, z)
    controls.target.set(0, 0, 0)
    controls.update()
  }, [])

  // Initialize Three.js WebGL scene, lights, helpers, and OrbitControls once.
  useEffect(() => {
    const container = mountRef.current
    if (!container) return

    const origMaterials = originalMaterialsRef.current
    const wireOverlays = wireOverlaysRef.current

    let renderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    } catch {
      setWebglError('WebGL is unavailable in this browser or graphics context. Enable hardware acceleration to inspect 3D scans.')
      return
    }

    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#0c100e')

    const width = Math.max(1, container.clientWidth)
    const height = Math.max(1, container.clientHeight)
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.01, 500)
    camera.position.set(2.1, 1.35, 2.3)

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setSize(width, height)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.0
    container.innerHTML = ''
    container.appendChild(renderer.domElement)

    const onContextLost = (e) => {
      e.preventDefault()
      setWebglError('WebGL rendering context was lost. Reload the page or reduce asset size.')
    }
    const onContextRestored = () => setWebglError(null)
    renderer.domElement.addEventListener('webglcontextlost', onContextLost)
    renderer.domElement.addEventListener('webglcontextrestored', onContextRestored)

    const ambient = new THREE.AmbientLight(0xffffff, 0.65)
    const key = new THREE.DirectionalLight(0xffffff, 1.2)
    key.position.set(4, 6, 5)
    const fill = new THREE.DirectionalLight(0xb8d8ff, 0.5)
    fill.position.set(-4, 2, -4)
    const rim = new THREE.DirectionalLight(0xd8f3e5, 0.35)
    rim.position.set(0, -3, -3)
    scene.add(ambient, key, fill, rim)

    const grid = new THREE.GridHelper(6, 24, 0x2f4038, 0x1a231f)
    grid.position.y = -1.12
    const axes = new THREE.AxesHelper(1.35)
    axes.position.set(-1.35, -1.11, -1.35)
    scene.add(grid, axes)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.06
    controls.enablePan = true
    controls.enableZoom = true
    controls.minDistance = 0.25
    controls.maxDistance = 35
    controls.autoRotateSpeed = 1.6

    clayMaterialRef.current = new THREE.MeshStandardMaterial({
      color: 0xcbd5cf,
      roughness: 0.8,
      metalness: 0.05,
      side: THREE.DoubleSide,
    })

    sceneRef.current = scene
    rendererRef.current = renderer
    cameraRef.current = camera
    controlsRef.current = controls
    helpersRef.current = { grid, axes }
    lightsRef.current = { ambient, key, fill }

    const ro = new ResizeObserver(([entry]) => {
      const { width: w, height: h } = entry.contentRect
      if (w > 0 && h > 0) {
        camera.aspect = w / h
        camera.updateProjectionMatrix()
        renderer.setSize(w, h)
      }
    })
    ro.observe(container)

    let rafId = 0
    const animate = () => {
      rafId = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }
    animate()

    return () => {
      cancelAnimationFrame(rafId)
      ro.disconnect()
      renderer.domElement.removeEventListener('webglcontextlost', onContextLost)
      renderer.domElement.removeEventListener('webglcontextrestored', onContextRestored)
      controls.dispose()

      for (const overlay of wireOverlays) {
        overlay.parent?.remove(overlay)
        overlay.geometry?.dispose?.()
        overlay.material?.dispose?.()
      }
      wireOverlays.length = 0

      if (modelRef.current) {
        scene.remove(modelRef.current)
        disposeThreeObject(modelRef.current)
        modelRef.current = null
      }
      origMaterials.clear()
      clayMaterialRef.current?.dispose?.()
      grid.geometry?.dispose?.()
      grid.material?.dispose?.()
      axes.geometry?.dispose?.()
      axes.material?.dispose?.()
      renderer.dispose()
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  // Sync OrbitControls, helpers, lighting, and shading mode.
  useEffect(() => {
    if (controlsRef.current) controlsRef.current.autoRotate = autoRotate
  }, [autoRotate])

  useEffect(() => {
    const { grid, axes } = helpersRef.current
    if (grid) grid.visible = showHelpers
    if (axes) axes.visible = showHelpers
  }, [showHelpers])

  useEffect(() => {
    const { ambient, key, fill } = lightsRef.current
    if (ambient) ambient.intensity = 0.65 * lightIntensity
    if (key) key.intensity = 1.2 * lightIntensity
    if (fill) fill.intensity = 0.5 * lightIntensity
  }, [lightIntensity])

  useEffect(() => {
    if (!modelRef.current || !clayMaterialRef.current) return
    setMaterialsAppearance(modelRef.current, {
      shadingMode,
      doubleSided,
      clayMaterial: clayMaterialRef.current,
      originalMaterials: originalMaterialsRef.current,
      wireOverlays: wireOverlaysRef.current,
    })
  }, [shadingMode, doubleSided, stats])

  // Keyboard shortcuts for fast inspection when an asset is loaded.
  useEffect(() => {
    function onKeyDown(e) {
      if (!files.obj) return
      const tag = e.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (e.key === 'r' || e.key === 'R') {
        moveCameraPreset('iso')
      } else if (e.key === 'w' || e.key === 'W') {
        setShadingMode((m) => (m === 'wireframe' ? 'textured' : 'wireframe'))
      } else if (e.code === 'Space') {
        e.preventDefault()
        setAutoRotate((r) => !r)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [files.obj, moveCameraPreset])

  // Load authorized user-supplied OBJ + optional MTL + optional texture files (zero fabricated geometry).
  useEffect(() => {
    const scene = sceneRef.current
    if (!scene) return

    for (const overlay of wireOverlaysRef.current) {
      overlay.parent?.remove(overlay)
      overlay.geometry?.dispose?.()
      overlay.material?.dispose?.()
    }
    wireOverlaysRef.current = []

    if (modelRef.current) {
      scene.remove(modelRef.current)
      disposeThreeObject(modelRef.current)
      modelRef.current = null
    }
    originalMaterialsRef.current.clear()
    setStats(null)
    setError(null)
    setNotices([])

    if (!files.obj) {
      setLoadingState({ active: false, percent: 0, stage: '' })
      return
    }

    let cancelled = false
    const createdUrls = []

    async function loadAsset() {
      const localNotices = []
      const textureNameByUuid = new Map()
      const textureNameByUrl = new Map()

      try {
        setLoadingState({ active: true, percent: 10, stage: 'Reading OBJ and MTL files…' })
        const [objText, mtlText] = await Promise.all([files.obj.text(), files.mtl ? files.mtl.text() : Promise.resolve(null)])
        if (cancelled) return

        const objMeta = inspectObjText(objText)
        if (!files.mtl && objMeta.mtllibs.length > 0) {
          localNotices.push(`OBJ references ${objMeta.mtllibs.join(', ')} — upload the matching .mtl file for original materials.`)
        }

        const texUrlByBasename = new Map()
        for (const tf of files.textures) {
          const url = URL.createObjectURL(tf)
          createdUrls.push(url)
          texUrlByBasename.set(tf.name.toLowerCase(), url)
          textureNameByUrl.set(url, tf.name)
        }

        let textureLoadDone = Promise.resolve()
        const manager = new THREE.LoadingManager()
        let pendingExternalTextures = 0

        if (mtlText) {
          const parsedMtl = parseMtlTextureReferences(mtlText)
          const { matched, missing } = matchMtlTextures(parsedMtl.referencedTextures, files.textures)
          pendingExternalTextures = matched.length
          if (missing.length > 0) {
            localNotices.push(
              `MTL references missing texture(s): ${missing.map((m) => m.basename).join(', ')}. Upload them to apply surface patterns.`,
            )
          }
        }

        if (pendingExternalTextures > 0) {
          textureLoadDone = new Promise((resolve) => {
            manager.onLoad = () => resolve()
            manager.onError = () => resolve()
          })
        }

        manager.onProgress = (_url, loaded, total) => {
          if (cancelled) return
          const pct = total > 0 ? 60 + Math.round((loaded / total) * 35) : 85
          setLoadingState({ active: true, percent: Math.min(95, pct), stage: `Loading textures (${loaded}/${total})…` })
        }

        // Resolve relative, nested, or Windows texture paths from MTL against uploaded texture blobs.
        manager.setURLModifier((requestedUrl) => {
          if (requestedUrl.startsWith('blob:') || requestedUrl.startsWith('data:')) return requestedUrl
          const base = basenameOf(requestedUrl).toLowerCase()
          if (base && texUrlByBasename.has(base)) {
            return texUrlByBasename.get(base)
          }
          // Return a 1x1 transparent PNG data URI for missing referenced textures so Three.js doesn't 404 to Vite.
          return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='
        })

        const objLoader = new OBJLoader(manager)
        if (mtlText) {
          setLoadingState({ active: true, percent: 30, stage: 'Parsing MTL materials…' })
          const mtlLoader = new MTLLoader(manager)
          const materials = mtlLoader.parse(mtlText, '')
          materials.preload()
          objLoader.setMaterials(materials)
        }

        setLoadingState({ active: true, percent: 50, stage: 'Parsing OBJ mesh geometry…' })
        // Yield once so progress bar paints before heavy synchronous OBJ parsing.
        await new Promise((r) => setTimeout(r, 16))
        if (cancelled) return

        const group = objLoader.parse(objText)

        // Direct albedo fallback when user uploads OBJ + texture image(s) without an MTL file.
        let directTexture = null
        let directTexName = null
        if (!mtlText && files.textures.length > 0) {
          setLoadingState({ active: true, percent: 75, stage: `Applying texture ${files.textures[0].name}…` })
          const first = files.textures[0]
          const firstUrl = texUrlByBasename.get(first.name.toLowerCase())
          if (firstUrl) {
            directTexture = await new Promise((res, rej) => new THREE.TextureLoader().load(firstUrl, res, undefined, rej))
            directTexture.colorSpace = THREE.SRGBColorSpace
            directTexture.name = first.name
            directTexName = first.name
            textureNameByUuid.set(directTexture.uuid, first.name)
          }
        }

        // Wait for any MTL-triggered async texture loads to finish before inspecting materials.
        await textureLoadDone
        if (cancelled) {
          disposeThreeObject(group)
          directTexture?.dispose?.()
          return
        }

        setLoadingState({ active: true, percent: 95, stage: 'Normalizing geometry & framing camera…' })
        let normalsComputed = false
        let meshCount = 0

        group.traverse((child) => {
          if (!child.isMesh || !child.geometry) return
          meshCount += 1
          if (!child.geometry.attributes?.normal || child.geometry.attributes.normal.count === 0) {
            child.geometry.computeVertexNormals()
            normalsComputed = true
          }

          if (directTexture) {
            child.material = new THREE.MeshStandardMaterial({
              name: `DirectTexture (${directTexName})`,
              map: directTexture,
              roughness: 0.72,
              metalness: 0.04,
              side: doubleSided ? THREE.DoubleSide : THREE.FrontSide,
            })
          } else if (!mtlText) {
            child.material = new THREE.MeshStandardMaterial({
              name: 'Default Neutral Surface',
              color: 0xd0d8d4,
              roughness: 0.75,
              metalness: 0.05,
              side: doubleSided ? THREE.DoubleSide : THREE.FrontSide,
            })
          } else {
            const mats = Array.isArray(child.material) ? child.material : [child.material]
            for (const mat of mats) {
              if (!mat) continue
              if (mat.map) {
                mat.map.colorSpace = THREE.SRGBColorSpace
                const src = mat.map.image?.currentSrc || mat.map.image?.src || ''
                if (textureNameByUrl.has(src)) {
                  textureNameByUuid.set(mat.map.uuid, textureNameByUrl.get(src))
                }
              }
              if (mat.emissiveMap) mat.emissiveMap.colorSpace = THREE.SRGBColorSpace
              mat.side = doubleSided ? THREE.DoubleSide : THREE.FrontSide
            }
          }
          originalMaterialsRef.current.set(child.uuid, child.material)
        })

        if (meshCount === 0) {
          disposeThreeObject(group)
          setError('The selected .obj file contained no renderable mesh geometry (no vertex/face data).')
          setLoadingState({ active: false, percent: 0, stage: '' })
          return
        }

        // Measure exact unscaled telemetry BEFORE normalizing display scale.
        const telemetry = extractMeshTelemetry(group, {
          rawFaceCount: objMeta.rawFaceCount,
          normalsComputed: normalsComputed || objMeta.declaredNormals === 0,
          textureNameByUuid,
        })

        // Auto-center and fit inside viewport cleanly.
        const box = new THREE.Box3().setFromObject(group)
        const size = box.getSize(new THREE.Vector3())
        const center = box.getCenter(new THREE.Vector3())
        const maxAxis = Math.max(size.x, size.y, size.z) || 1
        const scale = 2.25 / maxAxis
        group.scale.setScalar(scale)
        group.position.sub(center.multiplyScalar(scale))

        scene.add(group)
        modelRef.current = group

        if (clayMaterialRef.current) {
          setMaterialsAppearance(group, {
            shadingMode,
            doubleSided,
            clayMaterial: clayMaterialRef.current,
            originalMaterials: originalMaterialsRef.current,
            wireOverlays: wireOverlaysRef.current,
          })
        }

        moveCameraPreset('iso')
        setNotices(localNotices)
        setStats(telemetry)
        setLoadingState({ active: false, percent: 100, stage: '' })
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Could not parse the selected 3D asset files. Verify the .obj and .mtl syntax.')
          setLoadingState({ active: false, percent: 0, stage: '' })
        }
      }
    }

    loadAsset()
    return () => {
      cancelled = true
      for (const u of createdUrls) URL.revokeObjectURL(u)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [files, moveCameraPreset])

  function addFiles(fileList) {
    const next = classifyAssetFiles(fileList, files)
    const warnings = []
    if (next.ignored.length) {
      warnings.push(`Ignored unsupported file(s): ${next.ignored.join(', ')}. Supported: ${SUPPORTED_EXTENSIONS.join(', ')}.`)
    }
    if (next.oversized.length) {
      warnings.push(`Skipped file(s) larger than 150 MB: ${next.oversized.join(', ')}.`)
    }
    if (warnings.length) setNotices((prev) => [...warnings, ...prev])
    setFiles({ obj: next.obj, mtl: next.mtl, textures: next.textures })
  }

  // Server scans replace the current bundle instead of merging with it.
  function loadServerFiles(fileList) {
    const next = classifyAssetFiles(fileList, { obj: null, mtl: null, textures: [] })
    setNotices([])
    setFiles({ obj: next.obj, mtl: next.mtl, textures: next.textures })
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files)
  }

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-2 p-2.5">
        <label className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-control bg-accent px-3 text-xs font-medium text-accent-ink hover:bg-accent-strong">
          Load authorized OBJ / MTL / textures
          <input
            type="file"
            multiple
            accept={SUPPORTED_EXTENSIONS.join(',')}
            className="sr-only"
            onChange={(e) => {
              if (e.target.files?.length) addFiles(e.target.files)
              e.target.value = ''
            }}
          />
        </label>

        <span className="mx-1 hidden h-6 w-px bg-line sm:block" />

        <div role="radiogroup" aria-label="Shading mode" className="flex flex-wrap rounded-control border border-line bg-raised p-0.5">
          {SHADING_MODES.map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={shadingMode === id}
              disabled={!files.obj}
              onClick={() => setShadingMode(id)}
              className={cn(
                'h-8 rounded-[0.375rem] px-2.5 text-xs font-medium transition-colors disabled:opacity-40',
                shadingMode === id ? 'bg-surface text-accent shadow-card' : 'text-muted hover:text-ink',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {CAMERA_PRESETS.map(([id, label]) => (
            <Button key={id} size="sm" variant="secondary" disabled={!files.obj} onClick={() => moveCameraPreset(id)}>
              {label}
            </Button>
          ))}
          <Button size="sm" variant={autoRotate ? 'primary' : 'secondary'} disabled={!files.obj} onClick={() => setAutoRotate((r) => !r)}>
            {autoRotate ? 'Rotating' : 'Auto-rotate'}
          </Button>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {files.obj && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setFiles({ obj: null, mtl: null, textures: [] })
                setError(null)
                setNotices([])
              }}
            >
              Clear
            </Button>
          )}
          <Badge tone={webglError || error ? 'danger' : files.obj ? 'success' : 'neutral'}>
            {webglError ? 'WebGL error' : error ? 'Load error' : files.obj ? 'Authorized asset loaded' : 'Awaiting authorized scan'}
          </Badge>
        </div>
      </Card>

      <ServerScanPicker onLoaded={loadServerFiles} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card
          className={cn(
            'relative min-w-0 overflow-hidden transition-colors',
            dragging && 'border-accent ring-2 ring-accent/40',
          )}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <div ref={mountRef} className="h-[62vh] min-h-80 w-full bg-canvas lg:h-[calc(100vh-14.5rem)]" />

          {webglError && (
            <div className="absolute inset-0 flex items-center justify-center bg-canvas/95 p-6">
              <div className="max-w-md rounded-card border border-danger/40 bg-surface p-5 text-sm">
                <div className="font-semibold text-danger">WebGL renderer unavailable</div>
                <p className="mt-1.5 text-xs text-muted">{webglError}</p>
              </div>
            </div>
          )}

          {!webglError && loadingState.active && (
            <div className="absolute inset-0 flex items-center justify-center bg-canvas/80 p-6 backdrop-blur-xs">
              <div className="w-full max-w-sm rounded-card border border-line bg-surface p-5 space-y-3 shadow-card">
                <div className="flex items-center gap-2.5 text-sm font-medium text-ink">
                  <Spinner className="h-4 w-4 text-accent" />
                  <span>{loadingState.stage || 'Loading 3D scan…'}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-raised">
                  <div className="h-full bg-accent transition-all duration-150" style={{ width: `${loadingState.percent}%` }} />
                </div>
                <div className="tabular text-right font-mono text-xs text-faint">{loadingState.percent}%</div>
              </div>
            </div>
          )}

          {!webglError && !loadingState.active && !files.obj && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
              <EmptyState
                className="max-w-md rounded-card border border-dashed border-line-strong bg-surface/90 p-6 backdrop-blur"
                icon={<CubeIcon />}
                title={dragging ? 'Drop authorized 3D scan files here' : 'No authorized 3D hide scan loaded'}
                description="Drag and drop or select an authorized .obj mesh together with its optional .mtl material file and .jpg / .png / .webp textures. No synthetic zebra model is fabricated."
              />
            </div>
          )}

          {files.obj && stats && !loadingState.active && (
            <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-1.5">
              <Badge tone="neutral" className="bg-canvas/85 backdrop-blur">
                {stats.vertices.toLocaleString()} verts · {stats.triangles.toLocaleString()} tris
              </Badge>
              <Badge tone="neutral" className="bg-canvas/85 backdrop-blur">
                {shadingMode}
              </Badge>
            </div>
          )}
        </Card>

        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader
              eyebrow="Authorized assets"
              title="Loaded files"
              description="Processed locally in WebGL. Private 3D scans are never uploaded to the server."
            />
            <CardBody className="pt-2 text-xs space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-faint">OBJ mesh</span>
                <span className="truncate font-mono text-ink">
                  {files.obj ? `${files.obj.name} (${formatBytes(files.obj.size)})` : 'Not loaded'}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-faint">MTL material</span>
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate font-mono text-ink">{files.mtl ? files.mtl.name : 'None'}</span>
                  {files.mtl && (
                    <button
                      type="button"
                      onClick={() => setFiles((f) => ({ ...f, mtl: null }))}
                      className="text-danger hover:underline"
                    >
                      ×
                    </button>
                  )}
                </div>
              </div>
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-faint">Textures ({files.textures.length})</span>
                  {files.textures.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setFiles((f) => ({ ...f, textures: [] }))}
                      className="text-[0.6875rem] text-muted hover:text-ink"
                    >
                      Clear textures
                    </button>
                  )}
                </div>
                {files.textures.length === 0 ? (
                  <span className="text-faint">None</span>
                ) : (
                  <ul className="space-y-1 rounded-control border border-line bg-raised/60 p-2">
                    {files.textures.map((t) => (
                      <li key={t.name} className="flex items-center justify-between gap-2 font-mono text-[0.6875rem]">
                        <span className="truncate text-ink">{t.name}</span>
                        <button
                          type="button"
                          onClick={() => setFiles((f) => ({ ...f, textures: f.textures.filter((x) => x.name !== t.name) }))}
                          className="text-danger hover:underline"
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {error && (
                <div role="alert" className="rounded-control border border-danger/30 bg-danger/10 p-2.5 text-danger">
                  {error}
                </div>
              )}

              {notices.length > 0 && (
                <div className="space-y-1 rounded-control border border-warning/30 bg-warning/10 p-2.5 text-[0.6875rem] text-muted">
                  <div className="font-medium text-warning">Asset notices</div>
                  {notices.map((n, i) => (
                    <p key={i}>{n}</p>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader eyebrow="Mesh telemetry" title="Geometry statistics" />
            <CardBody className="pt-2 text-xs">
              {stats ? (
                <dl className="divide-y divide-line">
                  <div className="flex justify-between gap-2 py-1.5">
                    <dt className="text-faint">Sub-meshes</dt>
                    <dd className="tabular font-mono text-ink">{stats.meshes.toLocaleString()}</dd>
                  </div>
                  <div className="flex justify-between gap-2 py-1.5">
                    <dt className="text-faint">Vertices</dt>
                    <dd className="tabular font-mono text-ink">{stats.vertices.toLocaleString()}</dd>
                  </div>
                  <div className="flex justify-between gap-2 py-1.5">
                    <dt className="text-faint">Faces (OBJ / tris)</dt>
                    <dd className="tabular font-mono text-ink">
                      {stats.rawFaces.toLocaleString()} / {stats.triangles.toLocaleString()}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2 py-1.5">
                    <dt className="text-faint">Dimensions (X × Y × Z)</dt>
                    <dd className="tabular text-right font-mono text-ink">
                      {stats.boundingBox.x} × {stats.boundingBox.y} × {stats.boundingBox.z}
                    </dd>
                  </div>
                  <div className="flex justify-between gap-2 py-1.5">
                    <dt className="text-faint">Coordinate units</dt>
                    <dd className="text-right text-muted">Model units (uncalibrated)</dd>
                  </div>
                  <div className="flex justify-between gap-2 py-1.5">
                    <dt className="text-faint">UV coordinates</dt>
                    <dd className="text-ink">{stats.hasUVs ? 'Present' : 'Absent'}</dd>
                  </div>
                  <div className="flex justify-between gap-2 py-1.5">
                    <dt className="text-faint">Vertex normals</dt>
                    <dd className="text-ink">{stats.normalsStatus}</dd>
                  </div>
                </dl>
              ) : (
                <p className="text-faint">Load an authorized .obj scan to inspect real vertex, face, and dimension telemetry.</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader eyebrow="Surface shading" title="Loaded materials" />
            <CardBody className="pt-2 text-xs space-y-2">
              {stats?.materials?.length ? (
                <ul className="space-y-1.5">
                  {stats.materials.map((m, idx) => (
                    <li key={`${m.name}-${idx}`} className="rounded-control border border-line bg-raised/50 p-2 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex min-w-0 items-center gap-1.5 font-medium text-ink">
                          {m.colorHex && (
                            <span
                              className="inline-block h-3 w-3 shrink-0 rounded-sm border border-line-strong"
                              style={{ backgroundColor: m.colorHex }}
                            />
                          )}
                          <span className="truncate">{m.name}</span>
                        </span>
                        <Badge tone="neutral">{m.type.replace('Mesh', '').replace('Material', '') || 'Mat'}</Badge>
                      </div>
                      <div className="flex flex-wrap gap-1 text-[0.6875rem] text-faint">
                        <span>{m.hasMap ? `Map: ${m.mapName}` : 'No color map'}</span>
                        {m.hasNormalOrBump && <span>· Normal/Bump</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-faint">No materials loaded yet.</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader eyebrow="Display" title="Viewport & controls" />
            <CardBody className="pt-2 text-xs space-y-3">
              <label className="flex items-center justify-between gap-2 text-ink cursor-pointer">
                <span>Double-sided hide rendering</span>
                <input
                  type="checkbox"
                  checked={doubleSided}
                  onChange={(e) => setDoubleSided(e.target.checked)}
                  className="h-4 w-4 accent-[var(--color-accent)]"
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-ink cursor-pointer">
                <span>Reference grid & axes</span>
                <input
                  type="checkbox"
                  checked={showHelpers}
                  onChange={(e) => setShowHelpers(e.target.checked)}
                  className="h-4 w-4 accent-[var(--color-accent)]"
                />
              </label>
              <label className="block space-y-1">
                <div className="flex justify-between text-faint">
                  <span>Light intensity</span>
                  <span className="tabular font-mono text-ink">{lightIntensity.toFixed(1)}×</span>
                </div>
                <input
                  type="range"
                  min="0.4"
                  max="2.0"
                  step="0.1"
                  value={lightIntensity}
                  onChange={(e) => setLightIntensity(Number(e.target.value))}
                  className="w-full accent-[var(--color-accent)]"
                />
              </label>
              <div className="border-t border-line pt-2 text-[0.6875rem] text-muted space-y-0.5">
                <p>• Left-drag: orbit 360° · Scroll/pinch: zoom · Right-drag: pan</p>
                <p>• Shortcuts: <span className="font-mono text-ink">R</span> reset · <span className="font-mono text-ink">W</span> wireframe · <span className="font-mono text-ink">Space</span> rotate</p>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  )
}
