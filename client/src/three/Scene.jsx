import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Stars, Html } from "@react-three/drei";
import { useRef, useMemo, useState } from "react";
import * as THREE from "three";
import { useTelemetryStore } from "../store/telemetryStore";

// ตำแหน่งใน sim (หน่วยเมตร) หารด้วย WORLD_SCALE เพื่อให้พอดีกับ scene
// เปลี่ยนค่านี้ที่เดียวถ้าต้องการ rescale ทั้ง scene
const WORLD_SCALE = 1 / 2.5;


// ── Dish component ────────────────────────────────────────────────────────────

function Dish({ id, position, azDeg, elDeg, online, selected, tsysK, onSelect }) {
  const azGroupRef = useRef();
  const elGroupRef = useRef();
  const [hovered, setHovered] = useState(false);

  const targetAzRad = THREE.MathUtils.degToRad(-(azDeg - 180));
  // elevation: 90° = straight up (π/2), 0° = horizon
  const targetElRad = THREE.MathUtils.degToRad(elDeg - 90);

  useFrame((_, delta) => {
    if (!azGroupRef.current || !elGroupRef.current) return;
    const speed = online ? 0.8 : 0.1;
    azGroupRef.current.rotation.y = THREE.MathUtils.lerp(
      azGroupRef.current.rotation.y, targetAzRad, speed * delta * 3
    );
    elGroupRef.current.rotation.x = THREE.MathUtils.lerp(
      elGroupRef.current.rotation.x, targetElRad, speed * delta * 3
    );
  });

  const bodyColor = online ? (selected ? "#00ffcc" : hovered ? "#aaddff" : "#b8ccd8") : "#5a3333";
  const emissive  = online ? (selected ? "#003322" : "#0a1a2a") : "#1a0505";
  const legColor  = "#3a4a55";

  return (
    <group
      position={position}
      onPointerOver={() => { setHovered(true); document.body.style.cursor = "pointer"; }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = "default"; }}
      onClick={(e) => { e.stopPropagation(); onSelect(id); }}
    >
      {/* Base plate */}
      <mesh position={[0, 0.08, 0]} receiveShadow>
        <cylinderGeometry args={[0.22, 0.28, 0.16, 12]} />
        <meshStandardMaterial color="#2a3540" roughness={0.9} metalness={0.3} />
      </mesh>

      {/* Main column */}
      <mesh position={[0, 0.78, 0]} castShadow>
        <cylinderGeometry args={[0.065, 0.09, 1.4, 10]} />
        <meshStandardMaterial color={legColor} roughness={0.7} metalness={0.5} />
      </mesh>

      {/* AZ rotation group — rotates around Y axis */}
      <group ref={azGroupRef} position={[0, 1.5, 0]}>
        {/* Yoke arms */}
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * 0.18, 0.12, 0]} castShadow>
            <cylinderGeometry args={[0.04, 0.04, 0.24, 8]} />
            <meshStandardMaterial color={legColor} roughness={0.6} metalness={0.6} />
          </mesh>
        ))}

        {/* EL rotation group — rotates around X axis */}
        <group ref={elGroupRef} position={[0, 0.22, 0]}>
          {/* Dish bowl */}
          <mesh castShadow>
            <sphereGeometry args={[0.52, 28, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
            <meshStandardMaterial
              color={bodyColor}
              emissive={emissive}
              roughness={0.25}
              metalness={0.65}
              side={THREE.DoubleSide}
            />
          </mesh>

          {/* Feed horn struts × 4 */}
          {[0, 1, 2, 3].map((i) => {
            const a = (i / 4) * Math.PI * 2;
            return (
              <mesh
                key={i}
                position={[Math.cos(a) * 0.3, 0.28, Math.sin(a) * 0.3]}
                rotation={[Math.atan2(0.38, 0.3) * (i % 2 === 0 ? -1 : 1), a, 0]}
              >
                <cylinderGeometry args={[0.007, 0.007, 0.5, 5]} />
                <meshStandardMaterial color="#667788" metalness={0.8} roughness={0.3} />
              </mesh>
            );
          })}

          {/* Feed horn */}
          <mesh position={[0, 0.42, 0]}>
            <cylinderGeometry args={[0.03, 0.022, 0.18, 8]} />
            <meshStandardMaterial color="#99aa22" metalness={0.9} roughness={0.1} />
          </mesh>
          <mesh position={[0, 0.52, 0]}>
            <sphereGeometry args={[0.042, 10, 10]} />
            <meshStandardMaterial
              color={online ? "#aabb33" : "#553333"}
              emissive={online ? "#445500" : "#330000"}
              metalness={0.95}
            />
          </mesh>
        </group>
      </group>

      {/* Selection / hover ring */}
      {(selected || hovered) && (
        <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.3, 0.38, 32]} />
          <meshBasicMaterial
            color={selected ? "#00ffcc" : "#4488ff"}
            transparent
            opacity={selected ? 0.9 : 0.5}
          />
        </mesh>
      )}

      {/* Fault indicator */}
      {!online && (
        <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.28, 0.35, 24]} />
          <meshBasicMaterial color="#ff3333" transparent opacity={0.7} />
        </mesh>
      )}

      {/* Hover tooltip */}
      {hovered && (
        <Html distanceFactor={12} position={[0, 2.4, 0]} center>
          <div style={{
            background: "#07101acc", border: "1px solid #00d4ff44",
            padding: "3px 8px", borderRadius: 4, fontSize: 11,
            fontFamily: "monospace", color: "#00d4ff", whiteSpace: "nowrap",
          }}>
            {id} · {online ? `Tsys ${tsysK}K` : "OFFLINE"}
          </div>
        </Html>
      )}
    </group>
  );
}


// ── Large telescope (APEX, IRAM, etc.) ───────────────────────────────────────

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


// ── Terrain ───────────────────────────────────────────────────────────────────

function Terrain() {
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(900, 900, 80, 80);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      // undulation เล็กน้อยให้รู้สึกเป็น plateau จริง ไม่ใช่พื้นแบน
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
      <ambientLight intensity={0.25} color="#2a3d55" />
      <directionalLight
        position={[100, 160, 80]} intensity={1.6} color="#fffaea" castShadow
        shadow-mapSize-width={2048} shadow-mapSize-height={2048}
      />
      <pointLight position={[0, -8, 0]} intensity={0.1} color="#221a0a" />
      <hemisphereLight skyColor="#0d1a33" groundColor="#1a1208" intensity={0.4} />

      <Stars radius={350} depth={80} count={4000} factor={2.8} fade speed={0.2} />
      <Terrain />

      {alma.dishes.map((dish) => (
        <Dish
          key={dish.id}
          id={dish.id}
          position={[dish.x * WORLD_SCALE, 0, dish.z * WORLD_SCALE]}
          azDeg={dish.az_deg}
          elDeg={dish.el_deg}
          online={dish.online}
          selected={selectedId === dish.id}
          tsysK={dish.tsys_k}
          onSelect={onSelect}
        />
      ))}

      {large_telescopes.map((tel) => (
        <LargeTelescope
          key={tel.id}
          position={[tel.x * WORLD_SCALE, 0, tel.z * WORLD_SCALE]}
          diameterM={tel.diameter_m}
          online={tel.online}
          name={tel.name}
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