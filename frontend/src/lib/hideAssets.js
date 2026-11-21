import * as THREE from 'three'

export const SUPPORTED_OBJ_EXT = '.obj'
export const SUPPORTED_MTL_EXT = '.mtl'
export const SUPPORTED_TEXTURE_EXTS = ['.jpg', '.jpeg', '.png', '.webp']
export const SUPPORTED_EXTENSIONS = [SUPPORTED_OBJ_EXT, SUPPORTED_MTL_EXT, ...SUPPORTED_TEXTURE_EXTS]

// Soft browser memory safety cap per single file (150 MB).
export const MAX_ASSET_FILE_BYTES = 150 * 1024 * 1024

const MTL_MAP_DIRECTIVES = new Set([
  'map_kd',
  'map_ka',
  'map_ks',
  'map_ke',
  'map_ns',
  'map_d',
  'map_bump',
  'bump',
  'norm',
  'disp',
  'refl',
])

export const TEXTURE_MAP_SLOTS = [
  'map',
  'normalMap',
  'bumpMap',
  'roughnessMap',
  'metalnessMap',
  'specularMap',
  'alphaMap',
  'emissiveMap',
  'aoMap',
  'displacementMap',
]

export function extOf(name = '') {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

export function basenameOf(path = '') {
  const cleaned = String(path).trim().replace(/^["']|["']$/g, '')
  const parts = cleaned.split(/[/\\]/)
  return parts[parts.length - 1] || ''
}

/**
 * Merge newly chosen files into the current {obj, mtl, textures} asset bundle.
 * Tracks ignored unsupported files and oversized files explicitly without mutating input.
 */
export function classifyAssetFiles(fileList, existing = { obj: null, mtl: null, textures: [] }) {
  let obj = existing.obj ?? null
  let mtl = existing.mtl ?? null
  const textures = [...(existing.textures || [])]
  const ignored = []
  const oversized = []

  for (const file of Array.from(fileList || [])) {
    if (!file || !file.name) continue
    const ext = extOf(file.name)
    if (!SUPPORTED_EXTENSIONS.includes(ext)) {
      ignored.push(file.name)
      continue
    }
    if (typeof file.size === 'number' && file.size > MAX_ASSET_FILE_BYTES) {
      oversized.push(file.name)
      continue
    }
    if (ext === SUPPORTED_OBJ_EXT) {
      obj = file
    } else if (ext === SUPPORTED_MTL_EXT) {
      mtl = file
    } else {
      const key = file.name.toLowerCase()
      const idx = textures.findIndex((t) => t.name.toLowerCase() === key)
      if (idx >= 0) textures[idx] = file
      else textures.push(file)
    }
  }

  return { obj, mtl, textures, ignored, oversized }
}

/**
 * Extract the filename token from an MTL map_* directive line, skipping standard MTL options
 * such as `-bm 1.0`, `-s 1 1 1`, `-o 0 0 0`, `-clamp on`, `-blendu on`.
 */
function extractMtlMapPath(rest) {
  const trimmed = rest.trim()
  if (!trimmed) return ''
  const tokens = trimmed.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) || []
  let i = 0
  while (i < tokens.length) {
    const t = tokens[i]
    if (!t.startsWith('-')) return tokens.slice(i).join(' ').replace(/^["']|["']$/g, '')
    const flag = t.toLowerCase()
    if (flag === '-s' || flag === '-o' || flag === '-t') {
      i += 1
      let consumed = 0
      while (i < tokens.length && consumed < 3 && /^[+-]?\d*\.?\d+$/.test(tokens[i])) {
        i += 1
        consumed += 1
      }
    } else if (flag === '-mm') {
      i += 3
    } else if (['-bm', '-boost', '-clamp', '-blendu', '-blendv', '-cc', '-imfchan', '-texres', '-type'].includes(flag)) {
      i += 2
    } else {
      i += 1
    }
  }
  return ''
}

/**
 * Inspect an .mtl file to find declared material names and referenced texture files.
 */
export function parseMtlTextureReferences(mtlText = '') {
  const materialNames = []
  const referencedTextures = []
  let currentMaterial = '(default)'

  for (const rawLine of String(mtlText).split(/\r?\n/)) {
    const line = rawLine.replace(/#.*$/, '').trim()
    if (!line) continue
    const spaceIdx = line.search(/\s/)
    if (spaceIdx === -1) continue
    const directive = line.slice(0, spaceIdx).toLowerCase()
    const rest = line.slice(spaceIdx + 1).trim()
    if (directive === 'newmtl' && rest) {
      currentMaterial = rest
      if (!materialNames.includes(rest)) materialNames.push(rest)
    } else if (MTL_MAP_DIRECTIVES.has(directive)) {
      const rawPath = extractMtlMapPath(rest)
      const base = basenameOf(rawPath)
      if (base) {
        referencedTextures.push({
          material: currentMaterial,
          mapType: directive,
          rawPath,
          basename: base,
        })
      }
    }
  }

  return { materialNames, referencedTextures }
}

/**
 * Compare MTL-referenced textures against the user's uploaded texture files (case-insensitive basename).
 */
export function matchMtlTextures(referencedTextures = [], textureFiles = []) {
  const available = new Set(textureFiles.map((f) => basenameOf(f.name).toLowerCase()))
  const matched = []
  const missing = []
  const seenMissing = new Set()

  for (const ref of referencedTextures) {
    const key = ref.basename.toLowerCase()
    if (available.has(key)) {
      matched.push(ref)
    } else if (!seenMissing.has(key)) {
      seenMissing.add(key)
      missing.push(ref)
    }
  }
  return { matched, missing }
}

/**
 * Inspect raw OBJ text for declared mtllib references, usemtl names, and polygon face count.
 * Never fabricates statistics; counts only lines actually present in the OBJ text.
 */
export function inspectObjText(objText = '') {
  const mtllibs = []
  const usedMaterials = []
  let rawFaceCount = 0
  let declaredNormals = 0
  let declaredUVs = 0

  for (const rawLine of String(objText).split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    if (line.startsWith('f ') || line.startsWith('f\t')) {
      rawFaceCount += 1
    } else if (line.startsWith('vn ') || line.startsWith('vn\t')) {
      declaredNormals += 1
    } else if (line.startsWith('vt ') || line.startsWith('vt\t')) {
      declaredUVs += 1
    } else if (line.startsWith('mtllib ')) {
      const name = basenameOf(line.slice(7).trim())
      if (name && !mtllibs.includes(name)) mtllibs.push(name)
    } else if (line.startsWith('usemtl ')) {
      const name = line.slice(7).trim()
      if (name && !usedMaterials.includes(name)) usedMaterials.push(name)
    }
  }

  return { mtllibs, usedMaterials, rawFaceCount, declaredNormals, declaredUVs }
}

/**
 * Extract exact geometry and material telemetry from a parsed Three.js Object3D.
 * Bounding box is measured in the model's original unscaled coordinate space.
 */
export function extractMeshTelemetry(group, { rawFaceCount = null, normalsComputed = false, textureNameByUuid = new Map() } = {}) {
  let meshes = 0
  let vertices = 0
  let triangles = 0
  let hasUVs = false
  const materialMap = new Map()

  group.traverse((child) => {
    if (!child.isMesh || !child.geometry) return
    meshes += 1
    const geom = child.geometry
    const pos = geom.attributes?.position
    if (pos) vertices += pos.count
    if (geom.attributes?.uv && geom.attributes.uv.count > 0) hasUVs = true
    const idx = geom.index
    triangles += idx ? Math.floor(idx.count / 3) : Math.floor((pos?.count || 0) / 3)

    const mats = Array.isArray(child.material) ? child.material : child.material ? [child.material] : []
    for (const mat of mats) {
      const key = mat.uuid || mat.name || `mat-${materialMap.size}`
      if (materialMap.has(key)) continue
      const colorHex = mat.color && typeof mat.color.getHexString === 'function' ? `#${mat.color.getHexString()}` : null
      const mapName = mat.map ? textureNameByUuid.get(mat.map.uuid) || mat.map.name || 'Loaded texture' : null
      materialMap.set(key, {
        name: mat.name || '(unnamed material)',
        type: mat.type || 'Material',
        colorHex,
        hasMap: Boolean(mat.map),
        mapName,
        hasNormalOrBump: Boolean(mat.normalMap || mat.bumpMap),
      })
    }
  })

  const box = new THREE.Box3().setFromObject(group)
  const size = box.isEmpty() ? new THREE.Vector3(0, 0, 0) : box.getSize(new THREE.Vector3())

  return {
    meshes,
    vertices,
    triangles,
    rawFaces: rawFaceCount || triangles,
    hasUVs,
    normalsStatus: normalsComputed ? 'Computed from faces' : 'Embedded in OBJ',
    boundingBox: {
      x: Number(size.x.toFixed(4)),
      y: Number(size.y.toFixed(4)),
      z: Number(size.z.toFixed(4)),
    },
    materials: Array.from(materialMap.values()),
  }
}

/**
 * Thoroughly dispose all Three.js geometries, materials, and texture maps under an Object3D.
 */
export function disposeThreeObject(root) {
  if (!root) return
  const disposedMaterials = new Set()
  const disposedTextures = new Set()

  root.traverse((obj) => {
    if (obj.geometry && typeof obj.geometry.dispose === 'function') {
      obj.geometry.dispose()
    }
    if (obj.material) {
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
      for (const mat of mats) {
        if (!mat || disposedMaterials.has(mat)) continue
        disposedMaterials.add(mat)
        for (const slot of TEXTURE_MAP_SLOTS) {
          const tex = mat[slot]
          if (tex && !disposedTextures.has(tex) && typeof tex.dispose === 'function') {
            disposedTextures.add(tex)
            tex.dispose()
          }
        }
        if (typeof mat.dispose === 'function') mat.dispose()
      }
    }
  })
}
