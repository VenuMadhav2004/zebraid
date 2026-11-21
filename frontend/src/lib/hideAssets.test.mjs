import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'
import {
  classifyAssetFiles,
  disposeThreeObject,
  extractMeshTelemetry,
  inspectObjText,
  matchMtlTextures,
  parseMtlTextureReferences,
} from './hideAssets.js'

const SAMPLE_MTL = `
# Authorized scan test fixture
newmtl hide_surface
Ka 0.2 0.2 0.2
Kd 0.9 0.85 0.8
map_Kd -s 1 1 1 textures/zebra_flank.jpg
map_Bump -bm 0.5 C:\\scans\\zebra_normal.png
`

const SAMPLE_OBJ = `
mtllib zebra_scan.mtl
o flank_patch
v 0 0 0
v 2 0 0
v 2 1 0
v 0 1 0
vt 0 0
vt 1 0
vt 1 1
vt 0 1
usemtl hide_surface
f 1/1 2/2 3/3 4/4
`

test('classifyAssetFiles separates OBJ, MTL, textures, unsupported and oversized files', () => {
  const res = classifyAssetFiles([
    { name: 'scan.OBJ', size: 1024 },
    { name: 'scan.mtl', size: 256 },
    { name: 'albedo.jpg', size: 4096 },
    { name: 'ALBEDO.JPG', size: 8192 }, // replaces case-insensitively
    { name: 'notes.txt', size: 120 },
    { name: 'huge.obj', size: 200 * 1024 * 1024 },
  ])
  assert.equal(res.obj.name, 'scan.OBJ')
  assert.equal(res.mtl.name, 'scan.mtl')
  assert.equal(res.textures.length, 1)
  assert.equal(res.textures[0].size, 8192)
  assert.deepEqual(res.ignored, ['notes.txt'])
  assert.deepEqual(res.oversized, ['huge.obj'])
})

test('parseMtlTextureReferences & matchMtlTextures resolve paths and flag missing textures', () => {
  const parsed = parseMtlTextureReferences(SAMPLE_MTL)
  assert.deepEqual(parsed.materialNames, ['hide_surface'])
  assert.equal(parsed.referencedTextures.length, 2)
  assert.equal(parsed.referencedTextures[0].basename, 'zebra_flank.jpg')
  assert.equal(parsed.referencedTextures[1].basename, 'zebra_normal.png')

  const match = matchMtlTextures(parsed.referencedTextures, [{ name: 'ZEBRA_FLANK.JPG' }])
  assert.equal(match.matched.length, 1)
  assert.equal(match.missing.length, 1)
  assert.equal(match.missing[0].basename, 'zebra_normal.png')
})

test('inspectObjText detects mtllib, usemtl, quad faces and missing normals', () => {
  const info = inspectObjText(SAMPLE_OBJ)
  assert.deepEqual(info.mtllibs, ['zebra_scan.mtl'])
  assert.deepEqual(info.usedMaterials, ['hide_surface'])
  assert.equal(info.rawFaceCount, 1)
  assert.equal(info.declaredUVs, 4)
  assert.equal(info.declaredNormals, 0)
})

test('Three.js OBJLoader + MTLLoader + extractMeshTelemetry reports exact counts & dimensions', () => {
  const manager = new THREE.LoadingManager()
  const mtlLoader = new MTLLoader(manager)
  // Parse material definition without triggering browser DOM image loads in Node
  const mtlNoImage = SAMPLE_MTL.replace(/^map_.*$/gm, '')
  const materials = mtlLoader.parse(mtlNoImage, '')
  materials.preload()

  const objMeta = inspectObjText(SAMPLE_OBJ)
  const objLoader = new OBJLoader(manager)
  objLoader.setMaterials(materials)
  const group = objLoader.parse(SAMPLE_OBJ)

  let computedNormals = objMeta.declaredNormals === 0
  group.traverse((child) => {
    if (child.isMesh) {
      if (!child.geometry.attributes?.normal) {
        child.geometry.computeVertexNormals()
        computedNormals = true
      }
      assert.equal(child.geometry.attributes.normal.count, 6)
    }
  })
  assert.equal(computedNormals, true)

  const stats = extractMeshTelemetry(group, { rawFaceCount: 1, normalsComputed: computedNormals })
  assert.equal(stats.meshes, 1)
  assert.equal(stats.rawFaces, 1) // 1 quad in OBJ
  assert.equal(stats.triangles, 2) // triangulated into 2 tris
  assert.equal(stats.vertices, 6) // 2 unindexed tris -> 6 vertices
  assert.equal(stats.hasUVs, true)
  assert.equal(stats.normalsStatus, 'Computed from faces')
  assert.deepEqual(stats.boundingBox, { x: 2, y: 1, z: 0 })
  assert.equal(stats.materials.length, 1)
  assert.equal(stats.materials[0].name, 'hide_surface')
})

test('disposeThreeObject disposes geometry, material, and all texture map slots', () => {
  let geomDisposed = 0
  let matDisposed = 0
  let texDisposed = 0

  const tex = new THREE.Texture()
  tex.dispose = () => {
    texDisposed += 1
  }
  const mat = new THREE.MeshStandardMaterial({ map: tex })
  mat.dispose = () => {
    matDisposed += 1
  }
  const geom = new THREE.BufferGeometry()
  geom.dispose = () => {
    geomDisposed += 1
  }
  const mesh = new THREE.Mesh(geom, mat)
  const root = new THREE.Group()
  root.add(mesh)

  disposeThreeObject(root)
  assert.equal(geomDisposed, 1)
  assert.equal(matDisposed, 1)
  assert.equal(texDisposed, 1)
})
