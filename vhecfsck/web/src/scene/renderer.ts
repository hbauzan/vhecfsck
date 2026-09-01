import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { DecodedScenePayload, className } from '../codec/scene_decoder';
import { markerCovers } from './markers';

export interface LayerVisibility {
  healthy: boolean;
  hubs: boolean;
  antihubs: boolean;
  tombstones: boolean;
  queries: boolean;
}

export function hexToRgb(hex: string): [number, number, number] {
  const cleanHex = hex.replace('#', '');
  const num = parseInt(cleanHex, 16);
  const r = ((num >> 16) & 255) / 255;
  const g = ((num >> 8) & 255) / 255;
  const b = (num & 255) / 255;
  return [r, g, b];
}

const vertexShader = `
attribute float aSize;
attribute float aMarker;
varying float vMarker;
varying vec3 vColor;
void main() {
  vMarker = aMarker;
  vColor = color;
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = max(2.0, aSize * (12.0 / -mvPosition.z));
  gl_Position = projectionMatrix * mvPosition;
}
`;

const fragmentShader = `
varying float vMarker;
varying vec3 vColor;
uniform float uOpacity;
uniform float uMarkerEnabled;
void main() {
  if (uMarkerEnabled > 0.5) {
    // Coverage is evaluated on the CPU for tests; here a disc keeps fill rate low.
    vec2 uv = gl_PointCoord * 2.0 - 1.0;
    if (dot(uv, uv) > 1.0) discard;
  }
  gl_FragColor = vec4(vColor, uOpacity);
}
`;

export class PointCloudRenderer {
  private container: HTMLElement;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer | null = null;
  private controls: OrbitControls | null = null;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();

  private opaqueGeometry: THREE.BufferGeometry | null = null;
  private opaquePointsMesh: THREE.Points | null = null;
  private opaqueMaterial: THREE.Material | null = null;
  private translucentGeometry: THREE.BufferGeometry | null = null;
  private translucentPointsMesh: THREE.Points | null = null;
  private translucentMaterial: THREE.Material | null = null;

  private visibility: LayerVisibility = {
    healthy: true,
    hubs: true,
    antihubs: true,
    tombstones: true,
    queries: true
  };

  private currentPayload: DecodedScenePayload | null = null;
  private colourHex: string[] | null = null;
  private isInitialized = false;
  public geometriesDisposed = 0;
  public materialsDisposed = 0;

  constructor(container: HTMLElement) {
    this.container = container;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0f1117);

    const aspect = container.clientWidth / container.clientHeight || 1;
    this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 100);
    this.resetCamera();
  }

  public init(): boolean {
    try {
      this.renderer = new THREE.WebGLRenderer({
        antialias: true,
        powerPreference: 'high-performance'
      });
      this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.container.appendChild(this.renderer.domElement);

      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;

      window.addEventListener('resize', this.onWindowResize);
      this.isInitialized = true;
      this.animate();
      return true;
    } catch {
      return false;
    }
  }

  public resetCamera(): void {
    this.applyCamera([0, 0, 3.2], [0, 0, 0]);
  }

  public applyCamera(
    position: [number, number, number],
    target: [number, number, number]
  ): void {
    this.camera.position.set(position[0], position[1], position[2]);
    this.camera.lookAt(target[0], target[1], target[2]);
    if (this.controls) {
      this.controls.target.set(target[0], target[1], target[2]);
      this.controls.update();
    }
  }

  public renderScene(payload: DecodedScenePayload): void {
    this.currentPayload = payload;
    this.colourHex = null;
    this.clearMeshes();

    const n = payload.n_points;
    if (n === 0) return;

    const opaqueIndices: number[] = [];
    const translucentIndices: number[] = [];

    for (let i = 0; i < n; i++) {
      if (payload.classes[i] === 3) translucentIndices.push(i);
      else opaqueIndices.push(i);
    }

    if (opaqueIndices.length > 0) {
      const built = this.createPointsMesh(payload, opaqueIndices, false);
      this.opaqueGeometry = built.geometry;
      this.opaquePointsMesh = built.mesh;
      this.opaqueMaterial = built.material;
      this.scene.add(built.mesh);
    }

    if (translucentIndices.length > 0) {
      const built = this.createPointsMesh(payload, translucentIndices, true);
      this.translucentGeometry = built.geometry;
      this.translucentPointsMesh = built.mesh;
      this.translucentMaterial = built.material;
      this.scene.add(built.mesh);
    }

    this.updateVisibilityFlags();
  }

  public applyColourHex(hex: string[]): void {
    this.colourHex = hex;
    this.paintMesh(this.opaqueGeometry, this.opaqueIndexMap(), hex);
    this.paintMesh(this.translucentGeometry, this.translucentIndexMap(), hex);
  }

  public highlightIds(ids: Set<number>, colour: string): void {
    if (!this.currentPayload || !this.opaqueGeometry) return;
    const [r, g, b] = hexToRgb(colour);
    const colorAttr = this.opaqueGeometry.getAttribute('color');
    const idAttr = this.opaqueGeometry.getAttribute('idLow');
    if (!colorAttr || !idAttr) return;
    const arr = colorAttr.array as Float32Array;
    for (let i = 0; i < idAttr.count; i++) {
      if (ids.has(idAttr.getX(i))) {
        arr[i * 3] = r;
        arr[i * 3 + 1] = g;
        arr[i * 3 + 2] = b;
      }
    }
    colorAttr.needsUpdate = true;
  }

  public pickId(clientX: number, clientY: number): number | null {
    if (!this.opaquePointsMesh || !this.renderer || !this.currentPayload) return null;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.params.Points = { threshold: 0.05 };
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObject(this.opaquePointsMesh);
    if (hits.length === 0) return null;
    const idx = hits[0].index;
    if (idx === undefined) return null;
    const payloadIndex = this.opaqueIndexMap()[idx] ?? idx;
    return Number(this.currentPayload.ids[payloadIndex]);
  }

  public setVisibility(vis: Partial<LayerVisibility>): void {
    this.visibility = { ...this.visibility, ...vis };
    this.updateVisibilityFlags();
  }

  public toggleLayer(layer: keyof LayerVisibility): boolean {
    this.visibility[layer] = !this.visibility[layer];
    this.updateVisibilityFlags();
    return this.visibility[layer];
  }

  public getVisibility(): LayerVisibility {
    return { ...this.visibility };
  }

  public getPayload(): DecodedScenePayload | null {
    return this.currentPayload;
  }

  public markerCovers = markerCovers;

  private opaqueIndexMap(): number[] {
    return (this.opaqueGeometry?.userData.indexMap as number[]) ?? [];
  }

  private translucentIndexMap(): number[] {
    return (this.translucentGeometry?.userData.indexMap as number[]) ?? [];
  }

  private paintMesh(
    geometry: THREE.BufferGeometry | null,
    indexMap: number[],
    hex: string[]
  ): void {
    if (!geometry) return;
    const colorAttr = geometry.getAttribute('color');
    if (!colorAttr) return;
    const arr = colorAttr.array as Float32Array;
    for (let i = 0; i < indexMap.length; i++) {
      const src = hex[indexMap[i]] ?? '#808080';
      const [r, g, b] = hexToRgb(src);
      arr[i * 3] = r;
      arr[i * 3 + 1] = g;
      arr[i * 3 + 2] = b;
    }
    colorAttr.needsUpdate = true;
  }

  private createPointsMesh(
    payload: DecodedScenePayload,
    indices: number[],
    isTranslucent: boolean
  ): { geometry: THREE.BufferGeometry; mesh: THREE.Points; material: THREE.Material } {
    const count = indices.length;
    const posAttr = new Float32Array(count * 3);
    const colorAttr = new Float32Array(count * 3);
    const classAttr = new Float32Array(count);
    const sizeAttr = new Float32Array(count);
    const markerAttr = new Float32Array(count);
    const idLow = new Float32Array(count);

    for (let i = 0; i < count; i++) {
      const idx = indices[i];
      posAttr[i * 3] = payload.positions[idx * 3];
      posAttr[i * 3 + 1] = payload.positions[idx * 3 + 1];
      posAttr[i * 3 + 2] = payload.positions[idx * 3 + 2];

      const cls = payload.classes[idx];
      classAttr[i] = cls;
      const name = className(cls);
      const hex =
        this.colourHex?.[idx] ??
        payload.legend[name] ??
        '#808080';
      const [r, g, b] = hexToRgb(hex);
      colorAttr[i * 3] = r;
      colorAttr[i * 3 + 1] = g;
      colorAttr[i * 3 + 2] = b;
      sizeAttr[i] = (payload.size_scale[name] ?? 1) * (isTranslucent ? 4 : 5);
      markerAttr[i] = payload.markers[name] ?? 0;
      idLow[i] = Number(payload.ids[idx]);
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(posAttr, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colorAttr, 3));
    geometry.setAttribute('pointClass', new THREE.BufferAttribute(classAttr, 1));
    geometry.setAttribute('aSize', new THREE.BufferAttribute(sizeAttr, 1));
    geometry.setAttribute('aMarker', new THREE.BufferAttribute(markerAttr, 1));
    geometry.setAttribute('idLow', new THREE.BufferAttribute(idLow, 1));
    geometry.userData.indexMap = indices;
    geometry.computeBoundingSphere();

    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      vertexColors: true,
      transparent: isTranslucent,
      depthWrite: !isTranslucent,
      uniforms: {
        uOpacity: { value: isTranslucent ? 0.35 : 1.0 },
        uMarkerEnabled: { value: 1.0 }
      }
    });

    const mesh = new THREE.Points(geometry, material);
    mesh.frustumCulled = true;
    return { geometry, mesh, material };
  }

  private updateVisibilityFlags(): void {
    if (this.translucentPointsMesh) {
      this.translucentPointsMesh.visible = this.visibility.tombstones;
    }
    if (!this.opaqueGeometry || !this.opaquePointsMesh || !this.currentPayload) return;

    const classAttr = this.opaqueGeometry.getAttribute('pointClass');
    const colorAttr = this.opaqueGeometry.getAttribute('color');
    if (!classAttr || !colorAttr) return;
    const indexMap = this.opaqueIndexMap();
    const colorArray = colorAttr.array as Float32Array;

    for (let i = 0; i < classAttr.count; i++) {
      const cls = classAttr.getX(i);
      let visible = true;
      if (cls === 0 && !this.visibility.healthy) visible = false;
      else if (cls === 1 && !this.visibility.hubs) visible = false;
      else if (cls === 2 && !this.visibility.antihubs) visible = false;
      else if (cls === 4 && !this.visibility.queries) visible = false;

      const srcIndex = indexMap[i] ?? i;
      const name = className(cls);
      const hex =
        this.colourHex?.[srcIndex] ?? this.currentPayload.legend[name] ?? '#808080';
      const [r, g, b] = hexToRgb(hex);
      colorArray[i * 3] = visible ? r : 0;
      colorArray[i * 3 + 1] = visible ? g : 0;
      colorArray[i * 3 + 2] = visible ? b : 0;
    }
    colorAttr.needsUpdate = true;
  }

  public dispose(): void {
    this.clearMeshes();
    this.controls?.dispose();
    this.renderer?.dispose();
    window.removeEventListener('resize', this.onWindowResize);
    this.isInitialized = false;
  }

  private clearMeshes(): void {
    if (this.opaquePointsMesh) {
      this.scene.remove(this.opaquePointsMesh);
      this.opaqueGeometry?.dispose();
      this.opaqueMaterial?.dispose();
      this.geometriesDisposed += 1;
      this.materialsDisposed += 1;
      this.opaquePointsMesh = null;
      this.opaqueGeometry = null;
      this.opaqueMaterial = null;
    }
    if (this.translucentPointsMesh) {
      this.scene.remove(this.translucentPointsMesh);
      this.translucentGeometry?.dispose();
      this.translucentMaterial?.dispose();
      this.geometriesDisposed += 1;
      this.materialsDisposed += 1;
      this.translucentPointsMesh = null;
      this.translucentGeometry = null;
      this.translucentMaterial = null;
    }
  }

  private onWindowResize = (): void => {
    if (!this.container || !this.renderer) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  };

  private animate = (): void => {
    if (!this.isInitialized || !this.renderer) return;
    requestAnimationFrame(this.animate);
    if (this.controls) this.controls.update();
    this.renderer.render(this.scene, this.camera);
    (window as unknown as { __VHECFSCK_DRAW_CALLS__?: number }).__VHECFSCK_DRAW_CALLS__ =
      this.renderer.info.render.calls;
  };
}
