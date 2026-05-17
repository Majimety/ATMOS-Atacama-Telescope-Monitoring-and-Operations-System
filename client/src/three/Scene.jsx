import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars, Html } from "@react-three/drei";
import { useRef, useMemo, useState, Suspense } from "react";
import * as THREE from "three";
import { useTelemetryStore } from "../store/telemetryStore";
import DishMesh from "./DishMesh";

/**
 * Scene.jsx — Three.js canvas หลักของ ATMOS
 *
 * การเปลี่ยนแปลงจากเดิม:
 *   - Dish component ถูกแทนด้วย <DishMesh> ที่ load alma.glb จริง
 *   - ครอบ <Suspense> สำหรับ GLB loading — แสดง fallback ขณะโหลด
 *   - ลบ Dish inline component ออก (ย้ายไป DishMesh.jsx แล้ว)
 *   - LargeTelescope และ Terrain ยังคงเป็น geometry เดิม
 */

const WORLD_SCALE = 1 / 2.5;

// ── GLB Loading fallback (แสดงระหว่างโหลด alma.glb ครั้งแรก) ────────────────
function DishFallback({ position }) {
  return (
    <group position={position}>
      <mesh position={[0, 0.8, 0]}>
        <cylinderGeometry args={[0.06, 0.09, 1.4, 8]} />
        <meshStandardMaterial color="#2a3a45" />
      </mesh>
      <mesh position={[0, 1.7, 0]}>
        <sphereGeometry args={[0.5, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#667788" wireframe />
      </mesh>
    </group>
  );
}

// ── Loading overlay (แสดงบน canvas ขณะ GLB load ครั้งแรก) ───────────────────
function LoadingHud() {
  return (
    <Html fullscreen>
      <div style={{
        position:   "absolute",
        bottom:     24,
        left:       "50%",
        transform:  "translateX(-50%)",
        background: "#06101a99",
        border:     "1px solid #00d4ff22",
        borderRadius: 4,
        padding:    "6px 18px",
        fontFamily: "monospace",
        fontSize:   11,
        color:      "#00d4ff88",
        letterSpacing: "0.1em",
        pointerEvents: "none",
      }}>
        LOADING ANTENNA MODEL…
      </div>
    </Html>
  );
}

// ── Large telescope (APEX, IRAM etc.) — geometry เดิม ────────────────────────
function LargeTelescope({ position, diameterM, online }) {
  const s = Math.min(diameterM / 10, 3.2);
  return (
    <group position={position}>
      <mesh position={[0, 0.9 * s, 0]}>
        <cylinderGeometry args={[0.09 * s, 0.15 * s, 1.8 * s, 10]} />
        <meshStandardMaterial color="#3a4a55" roughness={0.8} metalness={0.4} />
      </mesh>
      <mesh position={[0, 1.8 * s, 0]}>
        <sphereGeometry args={[0.55 * s, 24, 14, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial
          color={online ? "#a8c0cc" : "#553333"}
          roughness={0.3} metalness={0.55}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
}

// ── Terrain — geometry เดิม ───────────────────────────────────────────────────
function Terrain() {
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(900, 900, 80, 80);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const h = Math.sin(x * 0.012) * Math.cos(z * 0.015) * 2.5
              + Math.sin(x * 0.033 + z * 0.028) * 0.8;
      pos.setY(i, h - 1.5);
    }
    geo.computeVertexNormals();
    return geo;
  }, []);

  return (
    <>
      <mesh geometry={geometry} receiveShadow rotation={[-Math.PI / 2, 0, 0]}>
        <meshStandardMaterial color="#1c1710" roughness={1} />
      </mesh>
      <gridHelper args={[800, 80, "#22201a", "#1a1814"]} position={[0, -0.3, 0]} />
    </>
  );
}

// ── Scene content ─────────────────────────────────────────────────────────────
function SceneContent({ selectedId, onSelect }) {
  const snapshot = useTelemetryStore((s) => s.snapshot);
  if (!snapshot) return null;

  const { alma, large_telescopes } = snapshot;

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.25} color="#2a3d55" />
      <directionalLight
        position={[100, 160, 80]}
        intensity={1.6}
        color="#fffaea"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <pointLight position={[0, -8, 0]} intensity={0.1} color="#221a0a" />
      <hemisphereLight skyColor="#0d1a33" groundColor="#1a1208" intensity={0.4} />

      <Stars radius={350} depth={80} count={4000} factor={2.8} fade speed={0.2} />
      <Terrain />

      {/* ALMA dishes — ครอบ Suspense เพื่อ handle GLB loading */}
      <Suspense fallback={
        // ระหว่างโหลด GLB ครั้งแรก แสดง fallback geometry ทุก dish
        <>
          {alma.dishes.map((dish) => (
            <DishFallback
              key={dish.id}
              position={[dish.x * WORLD_SCALE, 0, dish.z * WORLD_SCALE]}
            />
          ))}
          <LoadingHud />
        </>
      }>
        {alma.dishes.map((dish) => (
          <DishMesh
            key={dish.id}
            id={dish.id}
            position={[dish.x * WORLD_SCALE, 0, dish.z * WORLD_SCALE]}
            azDeg={dish.az_deg}
            elDeg={dish.el_deg}
            online={dish.online}
            selected={selectedId === dish.id}
            tsysK={dish.tsys_k}
            diameterM={dish.diameter_m}
            onSelect={onSelect}
          />
        ))}
      </Suspense>

      {/* Large telescopes (APEX etc.) — geometry เดิม ไม่ต้องโหลด GLB */}
      {large_telescopes?.map((tel) => (
        <LargeTelescope
          key={tel.id}
          position={[tel.x * WORLD_SCALE, 0, tel.z * WORLD_SCALE]}
          diameterM={tel.diameter_m}
          online={tel.online}
        />
      ))}
    </>
  );
}

// ── Export ────────────────────────────────────────────────────────────────────
export default function Scene({ selectedId, onSelect }) {
  return (
    <Canvas
      camera={{ position: [0, 55, 110], fov: 52 }}
      style={{ background: "#020509" }}
      shadows
    >
      <SceneContent selectedId={selectedId} onSelect={onSelect} />
      <OrbitControls
        minDistance={12}
        maxDistance={400}
        maxPolarAngle={Math.PI / 2.05}
        target={[0, 3, 0]}
        enableDamping
        dampingFactor={0.08}
      />
    </Canvas>
  );
}