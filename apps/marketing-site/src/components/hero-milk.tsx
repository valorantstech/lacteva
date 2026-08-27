"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * The living milk (LACTEVA-MARKETING-002; owner direction 2026-08-27:
 * the collection-centre milk can, transparent, with an Indian dairy
 * farmer — realistic flat style, true to scale: the can is knee-high,
 * the farmer stands over it).
 *
 * Three layers, one 420×470 coordinate space, so the whole scene scales
 * as ONE responsive figure:
 *   1. the canvas — the real-time fluid: a spring-damped surface
 *      heightfield inside the can, fed by milk drops born at the lip of
 *      the farmer's steel pot; each drop stretches under gravity and
 *      lands with a plop, a ripple ring and a crown of micro-droplets;
 *   2. the static fallback — the same milk, still, plus CSS drips
 *      (hidden under reduced motion: calm milk reads as design, drops
 *      frozen mid-air read as a glitch);
 *   3. the scene layer, always visible — the transparent can (outline,
 *      glass tint, wall reflections, ear handles) and the farmer:
 *      wrapped turban with its tail, mustache, kurta with placket and
 *      shoulder gamchha, dhoti, sandals, a steel pot tipped over the
 *      mouth.
 *
 * The can is ONE geometry: the same path strings clip the canvas fluid
 * (via Path2D) and draw the SVG, so the renderings cannot drift. No
 * library, no CDN, no shader. Purely decorative — the figure is
 * aria-hidden; every fact it could express is stated in the hero's text.
 */

// Design space, 420×470.
const W = 420;
const H = 470;
const COLS = 96;

// The milk can — knee-high, as the 20L can actually is: rolled rim,
// short neck, shoulder, straight body, bottom rim band.
const CAN_OUTER_D =
  "M98 256H182Q188 256 188 262V264Q188 270 182 270H180V288" +
  "C180 300 202 304 202 322V420Q206 424 206 430V432Q206 440 198 440H82" +
  "Q74 440 74 432V430Q74 424 78 420V322" +
  "C78 304 100 300 100 288V270H98Q92 270 92 264V262Q92 256 98 256Z";
const CAN_INTERIOR_D =
  "M108 273V290C108 306 86 310 86 324V424Q86 432 96 432H184" +
  "Q194 432 194 424V324C194 306 172 310 172 290V273Z";
const CAN_HANDLE_R_D = "M202 296C218 294 222 310 210 318L205 311C210 308 210 302 202 302Z";
const CAN_HANDLE_L_D = "M78 296C62 294 58 310 70 318L75 311C70 308 70 302 78 302Z";

const CAN = { cx: 140, surfHalf: 54, bottom: 436 };
const SURFACE_Y = 340; // resting milk line inside the can
const MAX_DEFLECT = 10;

// Where the farmer's pot pours from, and how the milk falls. Drops only
// start once he has walked in and tipped the pot (the CSS choreography
// runs 2.4s walk + 0.7s tip on the same clock).
const POUR = { x: 154, y: 186 };
const POUR_STARTS_AT = 3.0; // seconds into the simulation
const GRAVITY = 620; // design px/s²
const DROP_START_VY = 50;

// Watchdog: during the first ~2s of simulation, if most frames miss even a
// 30fps budget the device has told us everything — fall back to the scene.
const PROBE_FRAMES = 90;
const SLOW_FRAME_MS = 34;
const SLOW_LIMIT = 45;

type Ring = { x: number; r: number; life: number };
type Drop = { x: number; y: number; vy: number; size: number };
type Splash = { x: number; y: number; vx: number; vy: number; r: number; life: number };

function colX(i: number): number {
  return CAN.cx - CAN.surfHalf + (i / (COLS - 1)) * CAN.surfHalf * 2;
}

function colAt(x: number): number {
  const i = Math.round(
    ((x - (CAN.cx - CAN.surfHalf)) / (CAN.surfHalf * 2)) * (COLS - 1),
  );
  return Math.max(2, Math.min(COLS - 3, i));
}

export function HeroMilk({ className }: { className?: string }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;

    let ctx: CanvasRenderingContext2D | null = null;
    let reduced: MediaQueryList | null = null;
    try {
      if (typeof window.matchMedia === "function") {
        reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
        if (reduced.matches) return;
      }
      ctx = canvas.getContext("2d");
    } catch {
      return;
    }
    if (!ctx) return;
    const g = ctx;

    const interior = new Path2D(CAN_INTERIOR_D);

    // — Simulation state —
    const heights = new Float32Array(COLS);
    const vels = new Float32Array(COLS);
    const rings: Ring[] = [];
    const drops: Drop[] = [];
    const splashes: Splash[] = [];
    let t = 0;
    let raf = 0;
    let running = true;
    let dead = false;
    let frames = 0;
    let slow = 0;
    let last = performance.now();
    let scale = 1;
    let pointerX = -1;
    let lastPointerX = -1;
    let ringCooldown = 0;
    let dropCount = 0;
    let nextDropIn = 0.1;

    const die = () => {
      if (dead) return;
      dead = true;
      running = false;
      cancelAnimationFrame(raf);
      wrap.dataset.motion = "static";
    };

    const fit = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = wrap.clientWidth || 1;
      const h = wrap.clientHeight || 1;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      scale = (w / W) * dpr;
    };

    const surfaceAt = (x: number) => {
      const i = colAt(x);
      return SURFACE_Y + heights[i];
    };

    const plop = (x: number, strength: number) => {
      const c = colAt(x);
      vels[c] += strength;
      vels[c - 1] += strength * 0.55;
      vels[c + 1] += strength * 0.55;
      if (rings.length < 6) rings.push({ x, r: 5, life: 1 });
    };

    const step = () => {
      const dt = 1 / 60;

      // The next drop, from the pot's lip — but not before the farmer has
      // walked in and tipped it. Sized and timed with a little
      // deterministic variety (no Math.random: the pattern needs no state
      // and never repeats visibly).
      nextDropIn -= dt;
      if (nextDropIn <= 0 && t >= POUR_STARTS_AT) {
        dropCount += 1;
        drops.push({
          x: POUR.x + Math.sin(dropCount * 2.4) * 4,
          y: POUR.y,
          vy: DROP_START_VY,
          size: 6.5 + 1.8 * Math.sin(dropCount * 1.7),
        });
        nextDropIn = 0.55 + 0.2 * Math.sin(dropCount * 2.9);
      }

      // Falling milk: gravity, then the landing — a plop scaled by how hard
      // it arrives, a ring, and a small crown of micro-droplets.
      for (let i = drops.length - 1; i >= 0; i--) {
        const d = drops[i];
        d.vy += GRAVITY * dt;
        d.y += d.vy * dt;
        const surface = surfaceAt(d.x);
        if (d.y + d.size * 0.5 >= surface) {
          plop(d.x, Math.min(2, d.vy * 0.004 * (d.size / 8)));
          for (let s = 0; s < 3; s++) {
            splashes.push({
              x: d.x + (s - 1) * d.size * 0.5,
              y: surface - 2,
              vx: (s - 1) * (24 + d.size * 2),
              vy: -(55 + d.vy * 0.15) - s * 7,
              r: 1.3 + (s === 1 ? 1 : 0.5),
              life: 1,
            });
          }
          drops.splice(i, 1);
        }
      }

      // Splash crown: tiny milk beads arcing up and falling home.
      for (let i = splashes.length - 1; i >= 0; i--) {
        const s = splashes[i];
        s.vy += GRAVITY * dt;
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        s.life -= dt * 1.6;
        if (s.life <= 0 || s.y > surfaceAt(s.x) + 5) splashes.splice(i, 1);
      }

      // Cursor: the surface answers sideways motion under the pointer.
      if (pointerX >= 0 && lastPointerX >= 0) {
        const speed = Math.min(Math.abs(pointerX - lastPointerX), 40);
        if (speed > 0.5) {
          const c = colAt(pointerX);
          const amp = Math.min(speed * 0.045, 1);
          vels[c] += amp;
          vels[c - 1] += amp * 0.6;
          vels[c + 1] += amp * 0.6;
          if (speed > 12 && ringCooldown <= 0) {
            rings.push({ x: pointerX, r: 8, life: 1 });
            ringCooldown = 24;
          }
        }
      }
      lastPointerX = pointerX;
      ringCooldown -= 1;

      // Milk is never perfectly still: the faintest ambient swell.
      for (let i = 1; i < COLS - 1; i++) {
        vels[i] += Math.sin(t * 0.7 + i * 0.55) * 0.0018;
      }

      // Spring toward rest + neighbour tension, twice-damped: milk, not water.
      for (let i = 1; i < COLS - 1; i++) {
        const accel =
          0.02 * (heights[i - 1] + heights[i + 1] - 2 * heights[i]) -
          0.014 * heights[i];
        vels[i] = (vels[i] + accel) * 0.972;
      }
      for (let i = 0; i < COLS; i++) {
        heights[i] += vels[i];
        if (heights[i] > MAX_DEFLECT) heights[i] = MAX_DEFLECT;
        if (heights[i] < -MAX_DEFLECT) heights[i] = -MAX_DEFLECT;
      }
      // Spread passes make waves travel instead of standing.
      for (let pass = 0; pass < 2; pass++) {
        for (let i = 1; i < COLS - 1; i++) {
          vels[i - 1] += 0.11 * (heights[i] - heights[i - 1]);
          vels[i + 1] += 0.11 * (heights[i] - heights[i + 1]);
        }
      }
      // The meniscus: milk clings to the can wall.
      for (const i of [0, 1, 2, COLS - 3, COLS - 2, COLS - 1]) {
        heights[i] *= 0.82;
        vels[i] *= 0.82;
      }

      for (let i = rings.length - 1; i >= 0; i--) {
        rings[i].r += 0.7;
        rings[i].life -= 0.013;
        if (rings[i].life <= 0) rings.splice(i, 1);
      }
      t += dt;
    };

    const drawDrop = (d: Drop) => {
      // A falling drop: round belly, tapering tail — and it stretches as it
      // accelerates, the way liquid actually falls.
      const r = d.size;
      const e = 1 + Math.min(d.vy / 900, 0.55);
      g.beginPath();
      g.moveTo(d.x, d.y - r * 1.9 * e);
      g.bezierCurveTo(d.x - r * 0.95, d.y - r * 0.55, d.x - r, d.y + r * 0.4, d.x, d.y + r);
      g.bezierCurveTo(d.x + r, d.y + r * 0.4, d.x + r * 0.95, d.y - r * 0.55, d.x, d.y - r * 1.9 * e);
      g.closePath();
      g.fillStyle = "#FDFBF4";
      g.fill();
      g.beginPath();
      g.ellipse(d.x - r * 0.32, d.y - r * 0.1, r * 0.24, r * 0.38, -0.4, 0, Math.PI * 2);
      g.fillStyle = "rgba(255,255,255,0.85)";
      g.fill();
    };

    const draw = () => {
      g.setTransform(scale, 0, 0, scale, 0, 0);
      g.clearRect(0, 0, W, H);

      // 1 — the falling drops: in open air above the mouth, and the milk
      // paints over them below it, so a landing drop sinks under the
      // surface instead of popping away.
      for (const d of drops) drawDrop(d);

      // 2 — the milk, inside the transparent can. The interior clip does
      // the walls; the scene SVG above supplies the can itself.
      g.save();
      g.clip(interior);

      const left = CAN.cx - CAN.surfHalf;
      const right = CAN.cx + CAN.surfHalf;
      g.beginPath();
      g.moveTo(left - 4, SURFACE_Y + heights[0]);
      for (let i = 0; i < COLS - 1; i++) {
        const x0 = colX(i);
        const x1 = colX(i + 1);
        const y0 = SURFACE_Y + heights[i];
        const y1 = SURFACE_Y + heights[i + 1];
        g.quadraticCurveTo(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2);
      }
      g.lineTo(right + 4, SURFACE_Y + heights[COLS - 1]);
      g.lineTo(right + 8, CAN.bottom);
      g.lineTo(left - 8, CAN.bottom);
      g.closePath();
      const bg = g.createLinearGradient(left, SURFACE_Y - 8, right, CAN.bottom);
      bg.addColorStop(0, "#FFFFFF");
      bg.addColorStop(0.45, "#FDFBF4");
      bg.addColorStop(1, "#E4DEC9");
      g.fillStyle = bg;
      g.fill();

      // Depth at the bottom of the can.
      const shade = g.createLinearGradient(0, SURFACE_Y + 40, 0, CAN.bottom);
      shade.addColorStop(0, "rgba(27,94,32,0)");
      shade.addColorStop(1, "rgba(27,94,32,0.10)");
      g.fillStyle = shade;
      g.fillRect(left - 8, SURFACE_Y, CAN.surfHalf * 2 + 16, CAN.bottom - SURFACE_Y);

      // The crest: light catches the moving surface.
      g.beginPath();
      g.moveTo(left, SURFACE_Y + heights[0]);
      for (let i = 1; i < COLS; i++) {
        g.lineTo(colX(i), SURFACE_Y + heights[i]);
      }
      g.strokeStyle = "rgba(255,255,255,0.85)";
      g.lineWidth = 2;
      g.stroke();

      // The warm highlight, upper left of the milk body.
      const hl = g.createRadialGradient(
        CAN.cx - 26, SURFACE_Y + 34, 3,
        CAN.cx - 26, SURFACE_Y + 34, 44,
      );
      hl.addColorStop(0, "rgba(255,255,255,0.9)");
      hl.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = hl;
      g.fillRect(left, SURFACE_Y - 5, CAN.surfHalf * 2, 90);

      // Ripple rings riding the surface.
      for (const ring of rings) {
        g.beginPath();
        g.ellipse(ring.x, surfaceAt(ring.x) + 6, ring.r, ring.r * 0.28, 0, 0, Math.PI * 2);
        g.strokeStyle = `rgba(27,94,32,${(0.14 * ring.life).toFixed(3)})`;
        g.lineWidth = 1.4;
        g.stroke();
      }
      g.restore();

      // 3 — the splash crown, in front: milk answering milk.
      for (const s of splashes) {
        g.beginPath();
        g.arc(s.x, s.y, s.r * (0.6 + 0.4 * s.life), 0, Math.PI * 2);
        g.fillStyle = `rgba(253,251,244,${(0.9 * s.life).toFixed(3)})`;
        g.fill();
      }
    };

    const loop = (now: number) => {
      if (!running) return;
      const dt = now - last;
      last = now;
      if (frames < PROBE_FRAMES) {
        frames += 1;
        if (dt > SLOW_FRAME_MS) slow += 1;
        if (frames === PROBE_FRAMES && slow > SLOW_LIMIT) {
          die();
          return;
        }
      }
      // Fixed-step physics, capped so a background tab does not fast-forward.
      const steps = Math.min(Math.max(Math.round(dt / 16.7), 1), 3);
      for (let i = 0; i < steps; i++) step();
      draw();
      raf = requestAnimationFrame(loop);
    };

    const start = () => {
      if (dead || (running === true && raf !== 0)) return;
      running = true;
      last = performance.now();
      raf = requestAnimationFrame(loop);
    };
    const pause = () => {
      running = false;
      cancelAnimationFrame(raf);
      raf = 0;
    };

    const onPointerMove = (e: PointerEvent) => {
      const rect = wrap.getBoundingClientRect();
      pointerX = ((e.clientX - rect.left) / rect.width) * W;
    };
    const onPointerLeave = () => {
      pointerX = -1;
      lastPointerX = -1;
    };
    const onPointerDown = (e: PointerEvent) => {
      const rect = wrap.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * W;
      plop(x, 2.6);
    };
    const onReduce = () => {
      if (reduced?.matches) die();
    };

    let io: IntersectionObserver | null = null;
    let ro: ResizeObserver | null = null;
    try {
      fit();
      draw();
      wrap.dataset.motion = "live";
      start();

      ro = new ResizeObserver(fit);
      ro.observe(wrap);
      // Off-screen milk earns no frames.
      io = new IntersectionObserver(([entry]) => {
        if (dead) return;
        if (entry.isIntersecting) start();
        else pause();
      });
      io.observe(wrap);
      wrap.addEventListener("pointermove", onPointerMove);
      wrap.addEventListener("pointerdown", onPointerDown);
      wrap.addEventListener("pointerleave", onPointerLeave);
      reduced?.addEventListener("change", onReduce);
    } catch {
      die();
      return;
    }

    return () => {
      pause();
      dead = true;
      io?.disconnect();
      ro?.disconnect();
      wrap.removeEventListener("pointermove", onPointerMove);
      wrap.removeEventListener("pointerdown", onPointerDown);
      wrap.removeEventListener("pointerleave", onPointerLeave);
      reduced?.removeEventListener("change", onReduce);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      aria-hidden="true"
      data-motion="static"
      className={cn(
        "group relative mx-auto aspect-[420/470] w-full max-w-[420px] touch-pan-y select-none",
        className,
      )}
    >
      {/* Ground shadows — the can's and the farmer's. */}
      <div className="absolute bottom-[4.5%] left-[13%] h-[3.5%] w-[38%] rounded-full bg-black/30 blur-lg" />
      <div className="absolute right-[10%] bottom-[4.5%] h-[3.5%] w-[32%] rounded-full bg-black/25 blur-lg" />

      {/* The static milk: the server render, the no-JS page, and the
          fallback the canvas hands back to. Three CSS drips fall from the
          pot; compositor-only, hidden entirely under reduced motion. */}
      <div
        data-hero-static
        className="absolute inset-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-0"
      >
        {/* Positive delays: even the fallback drips wait for the farmer's
            walk (2.4s) and tip (0.7s) before the first milk falls. */}
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[38.5%] left-[34.5%] w-[4.5%]"
          style={{ "--drip-delay": "3.1s" } as React.CSSProperties}
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[38%] left-[36.5%] w-[4%]"
          style={{ "--drip-delay": "4s" } as React.CSSProperties}
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg
          data-hero-drip
          viewBox="0 0 24 34"
          className="hero-drip absolute top-[39%] left-[32.5%] w-[3.5%]"
          style={{ "--drip-delay": "4.9s" } as React.CSSProperties}
        >
          <path d="M12 2C15 11 20 15 20 23a8 8 0 1 1-16 0C4 15 9 11 12 2Z" fill="#FDFBF4" />
        </svg>
        <svg viewBox="0 0 420 470" className="absolute inset-0 size-full">
          <defs>
            <linearGradient id="hero-can-milk" x1="0.15" y1="0.4" x2="0.85" y2="1">
              <stop offset="0" stopColor="#FFFFFF" />
              <stop offset="0.45" stopColor="#FDFBF4" />
              <stop offset="1" stopColor="#E4DEC9" />
            </linearGradient>
            <radialGradient id="hero-can-glow" cx="0.38" cy="0.35" r="0.55">
              <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.9" />
              <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
            </radialGradient>
            <clipPath id="hero-can-clip">
              <path d={CAN_INTERIOR_D} />
            </clipPath>
          </defs>
          <g clipPath="url(#hero-can-clip)">
            <path
              d="M84 341Q112 336 140 340Q170 344 196 340L196 440H84Z"
              fill="url(#hero-can-milk)"
            />
            <path
              d="M86 341Q112 336 140 340Q170 344 194 340"
              fill="none"
              stroke="rgba(255,255,255,0.85)"
              strokeWidth="2"
            />
            <ellipse cx="118" cy="372" rx="30" ry="24" fill="url(#hero-can-glow)" />
            <ellipse
              cx="160" cy="356" rx="18" ry="5"
              fill="none" stroke="rgba(27,94,32,0.10)" strokeWidth="2"
            />
          </g>
        </svg>
      </div>

      <canvas
        ref={canvasRef}
        className="absolute inset-0 size-full opacity-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-100"
      />

      {/* The scene layer, always visible over whichever milk is live: the
          transparent can, and the farmer pouring from his steel pot. */}
      <svg viewBox="0 0 420 470" className="pointer-events-none absolute inset-0 size-full">
        <defs>
          <clipPath id="hero-can-scene-clip">
            <path d={CAN_INTERIOR_D} />
          </clipPath>
        </defs>

        {/* — The can: glass tint, wall reflections, silhouette, handles. — */}
        <g clipPath="url(#hero-can-scene-clip)">
          <rect x="74" y="250" width="132" height="192" fill="rgba(255,255,255,0.05)" />
          <path
            d="M96 300C90 340 90 392 96 426"
            fill="none" stroke="rgba(255,255,255,0.22)" strokeWidth="5"
          />
          <path
            d="M184 306C189 342 189 392 183 420"
            fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="3.5"
          />
        </g>
        <path d={CAN_OUTER_D} fill="none" stroke="rgba(253,251,244,0.6)" strokeWidth="3" />
        <path d={CAN_HANDLE_R_D} fill="rgba(253,251,244,0.6)" />
        <path d={CAN_HANDLE_L_D} fill="rgba(253,251,244,0.6)" />
        <ellipse
          cx="140" cy="258" rx="38" ry="4"
          fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="2"
        />

        {/* — The farmer. He WALKS in from the right (CSS: farmer-walk +
              the two leg groups swinging), arrives beside the can, and
              tips the pot (the farmer-pour group rotates down from the
              shoulder). Wrapped turban with its tail, a real face,
              kurta with placket, green gamchha, dhoti, sandals; the pot
              is a doodhwala's small steel can with its over-top handle.
              POUR is its lip. — */}
        <g className="farmer-walk">
          {/* legs, split so they can swing while he walks */}
          <g className="farmer-leg-a">
            <path d="M258 284L254 424H277L281 300Q270 288 258 284Z" fill="#FAF7EA" />
            <path d="M264 305Q262 350 266 395" fill="none" stroke="#E3DCC4" strokeWidth="1.5" />
            <ellipse cx="264" cy="427" rx="12" ry="5" fill="#C98A5B" />
            <path d="M252 432H278" stroke="#6B4A2F" strokeWidth="3.5" strokeLinecap="round" />
          </g>
          <g className="farmer-leg-b">
            <path d="M312 284L316 340 314 424H291L288 300Q300 288 312 284Z" fill="#FAF7EA" />
            <path d="M305 305Q307 350 303 395" fill="none" stroke="#E3DCC4" strokeWidth="1.5" />
            <ellipse cx="303" cy="427" rx="12" ry="5" fill="#C98A5B" />
            <path d="M291 432H317" stroke="#6B4A2F" strokeWidth="3.5" strokeLinecap="round" />
          </g>

          {/* kurta */}
          <path
            d="M262 138C250 146 246 172 244 200L240 262Q240 278 254 280L316 282Q328 280 327 264L322 200C320 170 314 146 305 138Q284 130 262 138Z"
            fill="#F5F1E3"
          />
          <path d="M284 142V202" stroke="#DDD5BD" strokeWidth="1.5" />
          <path d="M279 139L284 148L290 138" fill="none" stroke="#DDD5BD" strokeWidth="1.5" />
          <path d="M253 212Q251 242 254 268" fill="none" stroke="#E3DCC4" strokeWidth="1.5" />
          <path d="M312 214Q315 244 313 270" fill="none" stroke="#E3DCC4" strokeWidth="1.5" />
          {/* gamchha over the far shoulder */}
          <path d="M296 137L312 140L326 226L313 230Z" fill="#7FD495" />
          <path d="M316 219L325 217M317 224L326 222" stroke="#5CB877" strokeWidth="1.5" />

          {/* neck, and a face with real features: jaw, ears, hairline,
              eyes down on the pour, brows, nose, a full mustache */}
          <rect x="279" y="122" width="12" height="12" fill="#C98A5B" />
          <path
            d="M271 104Q271 96 279 94L291 94Q299 96 299 104L298 116Q297 127 285 128Q273 127 272 116Z"
            fill="#C98A5B"
          />
          <circle cx="269" cy="111" r="4" fill="#C98A5B" />
          <circle cx="301" cy="111" r="4" fill="#C98A5B" />
          <path d="M272 100Q285 94 298 100L298 104Q285 98 272 104Z" fill="#3E2C1E" />
          <ellipse cx="278.5" cy="107.5" rx="3" ry="2.4" fill="#FDFBF4" />
          <circle cx="277.8" cy="108.4" r="1.5" fill="#2A1D12" />
          <ellipse cx="291.5" cy="107.5" rx="3" ry="2.4" fill="#FDFBF4" />
          <circle cx="290.8" cy="108.4" r="1.5" fill="#2A1D12" />
          <path d="M274.5 103L283 101" stroke="#3E2C1E" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M287 101L295.5 103" stroke="#3E2C1E" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M286 105L284.5 113Q284.5 115.5 288 115.5" fill="none" stroke="#A9714A" strokeWidth="1.8" strokeLinecap="round" />
          <path
            d="M275 118Q285 123 295 118Q296 122 290 124.5Q285 126 280 124.5Q274 122 275 118Z"
            fill="#3E2C1E"
          />
          <path d="M282 128Q285 129.5 288 128" fill="none" stroke="#A9714A" strokeWidth="1.2" strokeLinecap="round" />
          {/* turban: wrapped, with a top fold and its tail */}
          <ellipse cx="285" cy="91" rx="27" ry="15" fill="#F1EDDD" transform="rotate(-8 285 91)" />
          <ellipse cx="280" cy="79" rx="13" ry="8" fill="#F1EDDD" />
          <path d="M262 91Q285 78 308 90" fill="none" stroke="#D9D2BA" strokeWidth="1.5" />
          <path d="M264 97Q285 86 306 96" fill="none" stroke="#D9D2BA" strokeWidth="1.5" />
          <path d="M305 95L312 121L305 123L300 99Z" fill="#E4DEC9" />

          {/* arms + hands + pot: one group, carried level on the walk in,
              rotated down from the shoulder to pour (CSS farmer-pour) */}
          <g className="farmer-pour" style={{ transformOrigin: "262px 158px" }}>
            {/* near arm to the handle, far arm under the base */}
            <path
              d="M256 148C226 150 196 152 172 156L174 168C200 162 228 158 258 162Z"
              fill="#F5F1E3"
            />
            <path
              d="M300 152C270 168 236 186 200 198L206 212C240 198 272 184 304 168Z"
              fill="#EFEAD8"
            />
            {/* the doodhwala's pot: tapered steel can, rim, collar band,
                over-top handle — drawn upright, tipped as one */}
            <g transform="rotate(-30 178 186)">
              <path
                d="M163 170L166 202Q178 208 190 202L193 170Z"
                fill="#D9D9D1" stroke="#BFBFB5" strokeWidth="1"
              />
              <path d="M166 197Q178 202 190 197" fill="none" stroke="#BFBFB5" strokeWidth="1" />
              <path d="M164 176Q178 181 192 176" fill="none" stroke="#BFBFB5" strokeWidth="1" />
              <ellipse cx="178" cy="170" rx="15" ry="4.5" fill="#EDEDE6" stroke="#BFBFB5" strokeWidth="1" />
              <path d="M164 168Q178 148 192 168" fill="none" stroke="#8F8F86" strokeWidth="2.5" />
              <path d="M168 176Q166 189 170 198" fill="none" stroke="rgba(255,255,255,0.75)" strokeWidth="2.5" />
            </g>
            {/* one hand on the handle, one under the base */}
            <circle cx="161" cy="157" r="7" fill="#C98A5B" />
            <circle cx="189" cy="203" r="7.5" fill="#B87C4F" />
            {/* milk at the pot's lip — where every drop is born; it only
                appears once the pour begins */}
            <ellipse className="pour-lip" cx="156" cy="182" rx="6" ry="3.2" fill="#FDFBF4" />
          </g>
        </g>
      </svg>
    </div>
  );
}
