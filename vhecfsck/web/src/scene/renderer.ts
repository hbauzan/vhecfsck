import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { DecodedScenePayload } from '../codec/scene_decoder';

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

export class PointCloudRenderer {
  private container: HTMLElement;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private renderer: THREE.WebGLRenderer | null = null;
  private controls: OrbitControls | null = null;

  private opaqueGeometry: THREE.BufferGeometry | null = null;
  private opaquePointsMesh: THREE.Points | null = null;
  private translucentGeometry: THREE.BufferGeometry | null = null;
  private translucentPointsMesh: THREE.Points | null = null;

  private visibility: LayerVisibility = {
    healthy: true,
    hubs: true,
    antihubs: true,
    tombstones: true,
    queries: true
  };

  private currentPayload: DecodedScenePayload | null = null;
  private isInitialized = false;

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
      this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
      this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

      this.container.appendChild(this.renderer.domElement);

      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;

      window.addEventListener('resize', this.onWindowResize.bind(this));
      this.isInitialized = true;
      this.animate();
      return true;
    } catch {
      return false;
    }
  }

  public resetCamera(): void {
    this.camera.position.set(0, 0, 3.2);
    this.camera.lookAt(0, 0, 0);
    if (this.controls) {
      this.controls.target.set(0, 0, 0);
      this.controls.update();
    }
  }

  public renderScene(payload: DecodedScenePayload): void {
    this.currentPayload = payload;
    this.clearMeshes();

    const n = payload.n_points;
    if (n === 0) return;

    const opaqueIndices: number[] = [];
    const translucentIndices: number[] = [];

    for (let i = 0; i < n; i++) {
      const cls = payload.classes[i];
      if (cls === 3) { // TOMBSTONE
        translucentIndices.push(i);
      } else {
        opaqueIndices.push(i);
      }
    }

    if (opaqueIndices.length > 0) {
      const { geometry, mesh } = this.createPointsMesh(payload, opaqueIndices, false);
      this.opaqueGeometry = geometry;
      this.opaquePointsMesh = mesh;
      this.scene.add(mesh);
    }

    if (translucentIndices.length > 0) {
      const { geometry, mesh } = this.createPointsMesh(payload, translucentIndices, true);
      this.translucentGeometry = geometry;
      this.translucentPointsMesh = mesh;
      this.scene.add(mesh);
    }

    this.updateVisibilityFlags();
  }

  private createPointsMesh(
    payload: DecodedScenePayload,
    indices: number[],
    isTranslucent: boolean
  ): { geometry: THREE.BufferGeometry; mesh: THREE.Points } {
    const count = indices.length;
    const posAttr = new Float32Array(count * 3);
    const colorAttr = new Float32Array(count * 3);
    const classAttr = new Float32Array(count);

    const defaultColors: Record<number, string> = {
      0: '#808080', // HEALTHY
      1: '#FF4D4D', // HUB
      2: '#4D79FF', // ANTIHUB
      3: '#4A4A4A', // TOMBSTONE
      4: '#FFD700', // QUERY
      5: '#00FF7F', // TRUE_NEIGHBOUR
      6: '#00BFFF', // RETURNED
      7: '#FF1493'  // MISSED
    };

    const colorCache: Record<number, [number, number, number]> = {};

    for (let i = 0; i < count; i++) {
      const idx = indices[i];
      const px = payload.positions[idx * 3];
      const py = payload.positions[idx * 3 + 1];
      const pz = payload.positions[idx * 3 + 2];

      posAttr[i * 3] = px;
      posAttr[i * 3 + 1] = py;
      posAttr[i * 3 + 2] = pz;

      const cls = payload.classes[idx];
      classAttr[i] = cls;

      if (!colorCache[cls]) {
        let hex = defaultColors[cls] || '#808080';
        if (payload.legend) {
          const classNameStr = ['HEALTHY', 'HUB', 'ANTIHUB', 'TOMBSTONE', 'QUERY', 'TRUE_NEIGHBOUR', 'RETURNED', 'MISSED'][cls];
          if (classNameStr && payload.legend[classNameStr]) {
            hex = payload.legend[classNameStr];
          }
        }
        colorCache[cls] = hexToRgb(hex);
      }

      const [r, g, b] = colorCache[cls];
      colorAttr[i * 3] = r;
      colorAttr[i * 3 + 1] = g;
      colorAttr[i * 3 + 2] = b;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(posAttr, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colorAttr, 3));
    geometry.setAttribute('pointClass', new THREE.BufferAttribute(classAttr, 1));

    const material = new THREE.PointsMaterial({
      size: isTranslucent ? 4 : 5,
      sizeAttenuation: true,
      vertexColors: true,
      transparent: isTranslucent,
      opacity: isTranslucent ? 0.35 : 1.0,
      depthWrite: !isTranslucent
    });

    const mesh = new THREE.Points(geometry, material);
    return { geometry, mesh };
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

  private updateVisibilityFlags(): void {
    if (!this.currentPayload) return;

    if (this.translucentPointsMesh) {
      this.translucentPointsMesh.visible = this.visibility.tombstones;
    }

    if (this.opaqueGeometry && this.opaquePointsMesh) {
      const classAttr = this.opaqueGeometry.getAttribute('pointClass');
      const colorAttr = this.opaqueGeometry.getAttribute('color');

      if (classAttr && colorAttr) {
        const count = classAttr.count;
        const colorArray = colorAttr.array as Float32Array;

        for (let i = 0; i < count; i++) {
          const cls = classAttr.getX(i);
          let visible = true;

          if (cls === 0 && !this.visibility.healthy) visible = false;
          else if (cls === 1 && !this.visibility.hubs) visible = false;
          else if (cls === 2 && !this.visibility.antihubs) visible = false;
          else if (cls === 4 && !this.visibility.queries) visible = false;

          // Hide point by zeroing opacity via color attribute or position
          // In Three.js vertexColors PointsMaterial, set RGB to 0,0,0 or position to NaN when hidden
          // To be clean, we can toggle individual mesh visibility or update color scale
          const defaultHexMap: Record<number, string> = {
            0: this.currentPayload.legend.HEALTHY || '#808080',
            1: this.currentPayload.legend.HUB || '#FF4D4D',
            2: this.currentPayload.legend.ANTIHUB || '#4D79FF',
            4: this.currentPayload.legend.QUERY || '#FFD700'
          };

          const [r, g, b] = hexToRgb(defaultHexMap[cls] || '#808080');

          if (visible) {
            colorArray[i * 3] = r;
            colorArray[i * 3 + 1] = g;
            colorArray[i * 3 + 2] = b;
          } else {
            colorArray[i * 3] = 0;
            colorArray[i * 3 + 1] = 0;
            colorArray[i * 3 + 2] = 0;
          }
        }
        colorAttr.needsUpdate = true;
      }
    }
  }

  private clearMeshes(): void {
    if (this.opaquePointsMesh) {
      this.scene.remove(this.opaquePointsMesh);
      this.opaqueGeometry?.dispose();
      this.opaquePointsMesh = null;
      this.opaqueGeometry = null;
    }
    if (this.translucentPointsMesh) {
      this.scene.remove(this.translucentPointsMesh);
      this.translucentGeometry?.dispose();
      this.translucentPointsMesh = null;
      this.translucentGeometry = null;
    }
  }

  private onWindowResize(): void {
    if (!this.container || !this.renderer) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  private animate(): void {
    if (!this.isInitialized || !this.renderer) return;
    requestAnimationFrame(this.animate.bind(this));
    if (this.controls) this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
