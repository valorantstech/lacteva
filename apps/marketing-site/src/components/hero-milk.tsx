"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * The living milk body (LACTEVA-MARKETING-002).
 *
 * The approved MarketingHero board is the composition; this makes it move:
 * a real-time 2D-canvas fluid — a spring-damped surface heightfield under
 * the board's blob, gradients and highlight — with a continuous pour stream
 * feeding it and cursor-reactive ripples on top. Everything is drawn from
 * this file; no library, no CDN, no shader.
 *
 * The static composition (the board, verbatim) is the server render, so it
 * is also the no-JS page, the reduced-motion page, and the weak-device
 * page: the canvas only fades in after the simulation has proven it can
 * hold a frame rate. If the first seconds jank, it bows out again.
 *
 * Purely decorative — the whole figure is aria-hidden; every fact it could
 * express is stated in the hero's text.
 */

// Design space (the board's 420×470 figure). All drawing happens in these
// coordinates; one scale factor maps them onto the actual canvas.
const W = 420;
const H = 470;
const COLS = 96;
const SURFACE_Y = 236; // resting surface at the rim
const DOME = 30; // the crown: the surface rises toward the middle, so the
// body reads as the board's soft pillow of milk, not a flat-topped bowl
// The live surface spans less than the belly: the shoulders bulge out
// below the rim, which is what makes the silhouette a pillow, not a bowl.
const BLOB = { cx: 210, surfHalf: 146, bodyHalf: 170, bottom: 430 };
const STREAM_W = 46;
const MAX_DEFLECT = 16;

// Watchdog: during the first ~2s of simulation, if most frames miss even a
// 30fps budget the device has told us everything — fall back to the board.
const PROBE_FRAMES = 90;
const SLOW_FRAME_MS = 34;
const SLOW_LIMIT = 45;

type Ring = { x: number; r: number; life: number };

function colX(i: number): number {
  return BLOB.cx - BLOB.surfHalf + (i / (COLS - 1)) * BLOB.surfHalf * 2;
}

function baseY(i: number): number {
  return SURFACE_Y - DOME * Math.sin(Math.PI * (i / (COLS - 1))) ** 0.9;
}

function colAt(x: number): number {
  const i = Math.round(
    ((x - (BLOB.cx - BLOB.surfHalf)) / (BLOB.surfHalf * 2)) * (COLS - 1),
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

    // — Simulation state —
    const heights = new Float32Array(COLS);
    const vels = new Float32Array(COLS);
    const rings: Ring[] = [];
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
    let stepCount = 0;

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

    const step = () => {
      // The pour lands just left of centre and sways gently, the way a
      // stream from a can does; it feeds the surface a steady push plus a
      // slow pulse so the milk is never still.
      const impactX = BLOB.cx + Math.sin(t * 0.9) * 6;
      const imp = colAt(impactX);
      // A pour presses the surface down; the milk answers around it.
      const push = 0.3 + 0.16 * Math.sin(t * 2.1);
      vels[imp] += push;
      vels[imp - 1] += push * 0.5;
      vels[imp + 1] += push * 0.5;

      // Cursor: the surface answers sideways motion under the pointer.
      if (pointerX >= 0 && lastPointerX >= 0) {
        const speed = Math.min(Math.abs(pointerX - lastPointerX), 40);
        if (speed > 0.5) {
          const c = colAt(pointerX);
          const amp = Math.min(speed * 0.045, 1.1);
          vels[c] += amp;
          vels[c - 1] += amp * 0.6;
          vels[c + 1] += amp * 0.6;
          if (speed > 12 && ringCooldown <= 0) {
            rings.push({ x: pointerX, r: 10, life: 1 });
            ringCooldown = 24;
          }
        }
      }
      lastPointerX = pointerX;
      ringCooldown -= 1;

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
      // The meniscus: the surface clings near the rim.
      for (const i of [0, 1, 2, COLS - 3, COLS - 2, COLS - 1]) {
        heights[i] *= 0.82;
        vels[i] *= 0.82;
      }

      // The pour's own quiet ripple, every few seconds.
      stepCount += 1;
      if (stepCount % 160 === 0 && rings.length < 6) {
        rings.push({ x: impactX + 26, r: 8, life: 1 });
      }
      for (let i = rings.length - 1; i >= 0; i--) {
        rings[i].r += 0.85;
        rings[i].life -= 0.012;
        if (rings[i].life <= 0) rings.splice(i, 1);
      }
      t += 1 / 60;
    };

    const surfaceAt = (x: number) => {
      const i = colAt(x);
      return baseY(i) + heights[i];
    };

    const draw = () => {
      g.setTransform(scale, 0, 0, scale, 0, 0);
      g.clearRect(0, 0, W, H);

      // 1 — the pour stream, top of frame into the surface.
      const impactX = BLOB.cx + Math.sin(t * 0.9) * 6;
      const streamBottom = surfaceAt(impactX) + 6;
      const sg = g.createLinearGradient(0, 0, 0, streamBottom);
      sg.addColorStop(0, "rgba(253,251,244,0.95)");
      sg.addColorStop(1, "#F1EDDD");
      g.fillStyle = sg;
      g.beginPath();
      g.moveTo(BLOB.cx - STREAM_W / 2, 0);
      g.bezierCurveTo(
        BLOB.cx - STREAM_W / 2,
        streamBottom * 0.55,
        impactX - STREAM_W * 0.34,
        streamBottom * 0.75,
        impactX - STREAM_W * 0.3,
        streamBottom,
      );
      g.lineTo(impactX + STREAM_W * 0.3, streamBottom);
      g.bezierCurveTo(
        impactX + STREAM_W * 0.34,
        streamBottom * 0.75,
        BLOB.cx + STREAM_W / 2,
        streamBottom * 0.55,
        BLOB.cx + STREAM_W / 2,
        0,
      );
      g.closePath();
      g.fill();

      // 2 — the milk body: live surface on top, the board's soft blob below.
      const left = BLOB.cx - BLOB.surfHalf;
      const right = BLOB.cx + BLOB.surfHalf;
      const yL = baseY(0) + heights[0];
      const yR = baseY(COLS - 1) + heights[COLS - 1];
      const body = new Path2D();
      body.moveTo(left, yL);
      for (let i = 0; i < COLS - 1; i++) {
        const x0 = colX(i);
        const x1 = colX(i + 1);
        const y0 = baseY(i) + heights[i];
        const y1 = baseY(i + 1) + heights[i + 1];
        body.quadraticCurveTo(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2);
      }
      body.lineTo(right, yR);
      // Round shoulders bulging past the rim, a full belly, back up the left
      // — the board's 46/54 organic radii, drawn as beziers.
      body.bezierCurveTo(
        BLOB.cx + BLOB.bodyHalf + 22, yR + 36,
        BLOB.cx + BLOB.bodyHalf + 12, BLOB.bottom - 58,
        BLOB.cx + 52, BLOB.bottom,
      );
      body.bezierCurveTo(
        BLOB.cx - 64, BLOB.bottom + 4,
        BLOB.cx - BLOB.bodyHalf - 18, BLOB.bottom - 64,
        left, yL,
      );
      body.closePath();

      const bg = g.createLinearGradient(left, SURFACE_Y - DOME - 10, right, BLOB.bottom);
      bg.addColorStop(0, "#FFFFFF");
      bg.addColorStop(0.45, "#FDFBF4");
      bg.addColorStop(1, "#E4DEC9");
      g.fillStyle = bg;
      g.fill(body);

      // Bottom shading — the board's inset green shadow.
      const shade = g.createLinearGradient(0, SURFACE_Y + 60, 0, BLOB.bottom);
      shade.addColorStop(0, "rgba(27,94,32,0)");
      shade.addColorStop(1, "rgba(27,94,32,0.10)");
      g.fillStyle = shade;
      g.fill(body);

      // 3 — the crest: light catches the moving surface.
      g.beginPath();
      g.moveTo(left + 3, baseY(0) + heights[0]);
      for (let i = 1; i < COLS; i++) {
        g.lineTo(colX(i), baseY(i) + heights[i]);
      }
      g.strokeStyle = "rgba(255,255,255,0.85)";
      g.lineWidth = 2;
      g.stroke();

      // 4 — the warm highlight, upper left, exactly where the board puts it.
      const hl = g.createRadialGradient(
        BLOB.cx - 95, SURFACE_Y + 18, 4,
        BLOB.cx - 95, SURFACE_Y + 18, 74,
      );
      hl.addColorStop(0, "rgba(255,255,255,0.9)");
      hl.addColorStop(1, "rgba(255,255,255,0)");
      g.save();
      g.clip(body);
      g.fillStyle = hl;
      g.fillRect(BLOB.cx - BLOB.bodyHalf, SURFACE_Y - DOME - 20, BLOB.bodyHalf * 2, 180);

      // 5 — ripple rings riding the surface (meniscus green, like the board's).
      for (const ring of rings) {
        g.beginPath();
        g.ellipse(ring.x, surfaceAt(ring.x) + 9, ring.r, ring.r * 0.3, 0, 0, Math.PI * 2);
        g.strokeStyle = `rgba(27,94,32,${(0.14 * ring.life).toFixed(3)})`;
        g.lineWidth = 1.6;
        g.stroke();
      }

      // 6 — a soft splash sheen where the pour lands.
      g.beginPath();
      g.ellipse(impactX, surfaceAt(impactX) + 3, 27, 5, 0, 0, Math.PI * 2);
      g.fillStyle = "rgba(255,255,255,0.35)";
      g.fill();
      g.restore();
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
      if (dead || running === true && raf !== 0) return;
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
      const c = colAt(x);
      vels[c] += 3;
      vels[c - 1] += 1.6;
      vels[c + 1] += 1.6;
      rings.push({ x, r: 12, life: 1 });
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
      {/* Ground shadow — under both renderings. */}
      <div className="absolute bottom-[3.5%] left-1/2 h-[4.7%] w-[71%] -translate-x-1/2 rounded-full bg-black/30 blur-lg" />

      {/* The approved board's static composition: the server render, the
          no-JS page, and the fallback the canvas hands back to. */}
      <div
        data-hero-static
        className="absolute inset-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-0"
      >
        <div className="hero-pour absolute top-0 left-1/2 h-[45%] w-[11%] -translate-x-1/2 rounded-b-3xl bg-[linear-gradient(180deg,rgba(253,251,244,0.95),#F1EDDD)]" />
        <div className="absolute bottom-[8.5%] left-1/2 h-[53%] w-[81%] -translate-x-1/2">
          <div className="absolute inset-0 rounded-[46%_54%_52%_48%/60%_58%_42%_40%] bg-[linear-gradient(160deg,#FFFFFF_0%,#FDFBF4_45%,#E4DEC9_100%)] shadow-[inset_0_-18px_34px_rgba(27,94,32,0.10),0_30px_60px_rgba(0,0,0,0.35)]" />
          <div className="absolute top-[15%] left-[18%] h-[26%] w-[32%] rounded-full bg-[radial-gradient(circle_at_40%_35%,rgba(255,255,255,0.95),rgba(255,255,255,0)_70%)]" />
          <div className="absolute right-[16%] bottom-[17%] h-[16%] w-[22%] rounded-full border-2 border-[rgba(27,94,32,0.10)]" />
          <div className="absolute bottom-[26%] left-[12%] h-[10.5%] w-[13.5%] rounded-full border border-[rgba(27,94,32,0.08)]" />
        </div>
      </div>

      <canvas
        ref={canvasRef}
        className="absolute inset-0 size-full opacity-0 transition-opacity duration-[var(--motion-slow)] group-data-[motion=live]:opacity-100"
      />
    </div>
  );
}
