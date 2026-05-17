import { useRef, useState, useMemo, useEffect } from "react";
import { useFrame } from "@react-three/fiber";
import { useGLTF, Html } from "@react-three/drei";
import * as THREE from "three";

/**
 * DishMesh — ALMA dish จาก alma.glb (NRAO 1/4 scale model)
 *
 * GLB node tree:
 *   american_with_barrier  scale=0.01, rot=+90°X
 *     almaVertex           scale=2.743, rot=-90°Z
 *       azimuth            scale=0.769, rot=+90°Z
 *         elevation_axis   rot=+90°Z    ← EL: rotate.z = deg(90-elDeg)
 *           dish bowl, feed, VertexRSIH
 *       fork
 *
 * AZ: root <group ref> rotation.y  (world Y, ไม่มี built-in interference)
 * EL: elevation_axis.rotation.z
 *     El=90°(zenith)→z=0, El=45°→z=+45°, El=0°(horizon)→z=+90°
 *
 * Scale:    MODEL_SCALE=0.2854  (fixed ทุก dish, dish bowl ≈ 2.5 units wide)
 * Z_OFFSET: 0.704  (center dish over group origin)
 * Y_OFFSET: 0      (ฐาน model อยู่ที่ Y=0 พอดี)
 *
 * Ring: วางที่ Y=0.02, radius inner=1.06, outer=1.31 (ตรงกับ dish footprint จริง)
 */

const MODEL_SCALE = 0.2854;
const Z_OFFSET    = 0.704;
const Y_OFFSET    = 0;

// ring fixed ตาม dish footprint จริง (ไม่ขึ้นกับ diameterM)
const RING_INNER  = 1.06;
const RING_OUTER  = 1.31;

useGLTF.preload("/alma.glb");

function cloneForInstance(src) {
  const clone = src.clone(true);
  clone.traverse((n) => {
    if (!n.isMesh) return;
    if (Array.isArray(n.material)) {
      n.material = n.material.map((m) => m.clone());
    } else if (n.material) {
      n.material = n.material.clone();
    }
  });
  return clone;
}

export default function DishMesh({
  id,
  position,
  azDeg     = 0,
  elDeg     = 45,
  online    = true,
  selected  = false,
  tsysK     = null,
  diameterM = 12,   // ยังรับ prop แต่ไม่ใช้ scale แล้ว (fixed MODEL_SCALE)
  onSelect,
}) {
  const [hovered, setHovered] = useState(false);
  const rootRef = useRef();   // AZ rotation — world Y

  const { scene: gltfScene } = useGLTF("/alma.glb");
  const clonedScene = useMemo(() => cloneForInstance(gltfScene), [gltfScene]);

  const elNode = useMemo(
    () => clonedScene.getObjectByName("elevation_axis"),
    [clonedScene]
  );

  // ── สี mesh ตาม state ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!clonedScene) return;
    const col = online
      ? selected  ? new THREE.Color("#00ffcc")
        : hovered ? new THREE.Color("#d8eef8")
        : new THREE.Color("#c8d8e4")
      : new THREE.Color("#6a3535");
    const emi = selected
      ? new THREE.Color("#003322")
      : new THREE.Color("#000000");

    clonedScene.traverse((n) => {
      if (!n.isMesh) return;
      const mats = Array.isArray(n.material) ? n.material : [n.material];
      mats.forEach((m) => {
        if (!m) return;
        if (m.color)  m.color.lerp(col, online ? 0.2 : 0.7);
        if (m.emissive) m.emissive.copy(emi);
        if ("emissiveIntensity" in m) m.emissiveIntensity = selected ? 0.3 : 0;
      });
    });
  }, [clonedScene, online, selected, hovered]);

  // ── Target rotations ───────────────────────────────────────────────────────
  // AZ: ALMA 0°=N CW+ → Three.js negate
  const targetAz = THREE.MathUtils.degToRad(-(azDeg - 180));

  // EL: elevation_axis local Z (built-in +90°Z ทำให้ sign = +(90-elDeg))
  const targetEl = THREE.MathUtils.degToRad(90 - elDeg);

  // ── Animation ──────────────────────────────────────────────────────────────
  useFrame((_, delta) => {
    if (!rootRef.current || !elNode) return;
    const t = Math.min(1, (online ? 3.0 : 0.4) * delta);

    // AZ shortest-path
    const curAz  = rootRef.current.rotation.y;
    const diffAz = ((targetAz - curAz + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
    rootRef.current.rotation.y = curAz + diffAz * t;

    // EL clamp [0, π/2]
    const clampedEl = Math.max(0, Math.min(Math.PI / 2, targetEl));
    elNode.rotation.z = THREE.MathUtils.lerp(elNode.rotation.z, clampedEl, t);
  });

  return (
    <group
      position={position}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true);  document.body.style.cursor = "pointer"; }}
      onPointerOut={()  => { setHovered(false); document.body.style.cursor = "default"; }}
      onClick={(e)      => { e.stopPropagation(); onSelect?.(id); }}
    >
      {/* AZ wrapper — world Y rotation */}
      <group ref={rootRef}>
        <primitive
          object={clonedScene}
          scale={[MODEL_SCALE, MODEL_SCALE, MODEL_SCALE]}
          position={[0, Y_OFFSET, 0]}
        />
      </group>

      {/* Selection / hover ring — อยู่นอก AZ group (world space) ที่ Y=0.02
          ไม่ใส่ Z offset เพราะ ring ต้องนอนราบบนพื้น world XZ plane */}
      {(selected || hovered) && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
          <ringGeometry args={[RING_INNER, RING_OUTER, 64]} />
          <meshBasicMaterial
            color={selected ? "#00ffcc" : "#4488ff"}
            transparent
            opacity={selected ? 0.9 : 0.45}
          />
        </mesh>
      )}

      {/* Offline ring */}
      {!online && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]}>
          <ringGeometry args={[RING_INNER * 0.85, RING_OUTER * 0.85, 40]} />
          <meshBasicMaterial color="#ff3333" transparent opacity={0.55} />
        </mesh>
      )}

      {/* Hover tooltip */}
      {hovered && (
        <Html
          distanceFactor={14}
          position={[0, 3.5, 0]}
          center
          style={{ pointerEvents: "none" }}
        >
          <div style={{
            background:     "#05101acc",
            border:         "1px solid #00d4ff44",
            backdropFilter: "blur(4px)",
            padding:        "3px 10px",
            borderRadius:   3,
            fontSize:       11,
            fontFamily:     "monospace",
            color:          "#00d4ff",
            whiteSpace:     "nowrap",
            letterSpacing:  "0.05em",
          }}>
            {id}
            {online
              ? tsysK != null ? ` · Tsys ${tsysK.toFixed(0)} K` : ""
              : " · OFFLINE"
            }
          </div>
        </Html>
      )}
    </group>
  );
}