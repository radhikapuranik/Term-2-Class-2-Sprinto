// Motion: GSAP is loaded lazily from the local npm copy after the page is already readable.
// Everything animates FROM its final, visible state, and only when the person allows motion.

const reduce = matchMedia("(prefers-reduced-motion: reduce)");
let loading;

function script(src) {
  return new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src; s.async = true; s.onload = ok; s.onerror = fail;
    document.head.appendChild(s);
  });
}

export function gsapReady() {
  if (reduce.matches) return Promise.resolve(null);
  loading ??= script("/vendor/gsap/gsap.min.js")
    .then(() => Promise.all([script("/vendor/gsap/ScrollTrigger.min.js"), script("/vendor/gsap/Flip.min.js")]))
    .then(() => {
      const { gsap, ScrollTrigger, Flip } = window;
      gsap.registerPlugin(ScrollTrigger, Flip);
      gsap.defaults({ ease: "expo.out", duration: 0.6 });
      document.documentElement.classList.add("motion");
      return gsap;
    })
    .catch(() => null); // no motion is fine: the page is already complete
  return loading;
}
export const motionOK = () => !reduce.matches;

// Run fn(gsap) only for people who allow motion; gsap.matchMedia reverts it if they switch.
export async function animate(fn) {
  const gsap = await gsapReady();
  if (!gsap) return;
  const mm = gsap.matchMedia();
  mm.add("(prefers-reduced-motion: no-preference)", () => fn(gsap));
  return mm;
}

export function countUp(el, to, { duration = 0.9, suffix = "" } = {}) {
  el.textContent = `${to}${suffix}`; // final value first: readable without JS motion
  animate((gsap) => {
    const o = { v: 0 };
    gsap.to(o, { v: to, duration, ease: "power2.out", onUpdate: () => { el.textContent = `${Math.round(o.v)}${suffix}`; } });
  });
}

export function drawPath(path, opts = {}) {
  animate((gsap) => {
    const len = path.getTotalLength();
    gsap.fromTo(path, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 0.8, ease: "power2.inOut", ...opts,
      onComplete: () => { path.style.strokeDasharray = ""; path.style.strokeDashoffset = ""; } });
  });
}

// Cards and sections slide up a little as they scroll in. Tables and banners are never animated.
export function reveal(root, sel = "[data-reveal]") {
  animate((gsap) => {
    const items = root.querySelectorAll(sel);
    if (!items.length) return;
    window.ScrollTrigger.batch(items, {
      start: "top 92%", once: true,
      onEnter: (batch) => gsap.from(batch, { y: 18, opacity: 0, duration: 0.6, stagger: 0.06, clearProps: "transform,opacity" }),
    });
  });
}

export function heroLines(root) {
  animate((gsap) => gsap.from(root.querySelectorAll(".line > span"), { yPercent: 105, duration: 0.75, stagger: 0.08, clearProps: "transform" }));
}

export function ringFill(root) {
  animate((gsap) => {
    root.querySelectorAll(".ring").forEach((r, i) => {
      gsap.from(r.querySelectorAll(".seg"), { opacity: 0, scale: 0.6, transformOrigin: "50% 50%", duration: 0.35, stagger: 0.05, delay: 0.1 + i * 0.03, clearProps: "all" });
    });
  });
}

// Small success burst: a few dots from the button, not a confetti storm.
export function burst(fromEl) {
  if (!motionOK()) return;
  const r = fromEl.getBoundingClientRect();
  const colors = ["var(--go)", "var(--highlight)", "var(--brand)"];
  for (let i = 0; i < 10; i++) {
    const d = document.createElement("i");
    d.className = "burst";
    d.style.left = `${r.left + r.width / 2}px`;
    d.style.top = `${r.top + r.height / 2}px`;
    d.style.background = colors[i % 3];
    document.body.appendChild(d);
    const a = (Math.PI * 2 * i) / 10 + Math.random() * 0.4, dist = 34 + Math.random() * 30;
    d.animate([{ transform: "translate(-50%,-50%) scale(1)", opacity: 1 },
      { transform: `translate(calc(-50% + ${Math.cos(a) * dist}px), calc(-50% + ${Math.sin(a) * dist}px)) scale(.3)`, opacity: 0 }],
    { duration: 650, easing: "cubic-bezier(.22,1,.36,1)" }).onfinish = () => d.remove();
  }
}

export function shake(el) {
  if (!motionOK()) return;
  el.animate([{ transform: "translateX(0)" }, { transform: "translateX(-6px)" }, { transform: "translateX(5px)" }, { transform: "translateX(-3px)" }, { transform: "translateX(0)" }],
    { duration: 360, easing: "ease-out" });
}

// Click feedback: ripple on every button; magnetic pull on primary buttons (desktop pointers only).
export function initFeedback() {
  document.addEventListener("pointerdown", (e) => {
    const b = e.target.closest(".btn");
    if (!b || b.disabled || !motionOK()) return;
    const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height) * 2.2;
    const dot = document.createElement("span");
    dot.className = "ripple";
    Object.assign(dot.style, { width: `${s}px`, height: `${s}px`, left: `${e.clientX - r.left - s / 2}px`, top: `${e.clientY - r.top - s / 2}px` });
    b.appendChild(dot);
    setTimeout(() => dot.remove(), 650);
  });
  if (!matchMedia("(hover: hover) and (pointer: fine)").matches) return;
  document.addEventListener("pointermove", (e) => {
    const b = e.target.closest(".btn.primary, .btn.go");
    document.querySelectorAll(".btn.magnet").forEach((m) => { if (m !== b) { m.classList.remove("magnet"); m.style.translate = ""; } });
    if (!b || b.disabled || !motionOK()) return;
    const r = b.getBoundingClientRect();
    b.classList.add("magnet");
    b.style.translate = `${(e.clientX - r.left - r.width / 2) * 0.12}px ${(e.clientY - r.top - r.height / 2) * 0.18}px`;
  });
}

// Page transition: a quick fade/slide of the view (a wipe on desktop).
export async function pageOut(view) {
  const gsap = await gsapReady();
  if (!gsap) return;
  await gsap.to(view, { opacity: 0, y: 6, duration: 0.16, ease: "power1.in" });
}
export async function pageIn(view) {
  const gsap = await gsapReady();
  if (!gsap) { view.style.opacity = ""; return; }
  gsap.fromTo(view, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.42, clearProps: "transform,opacity" });
}
