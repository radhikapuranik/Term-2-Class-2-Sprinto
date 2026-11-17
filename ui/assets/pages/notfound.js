import { html, icon, render } from "../lib.js";
import { heroLines } from "../motion.js";

export function render_(view) {
  render(view, html`<div class="page lost">
    <p class="eyebrow" style="justify-content:center">Error 404</p>
    <h1><span class="line"><span>Off the</span></span><span class="line"><span><em>map.</em></span></span></h1>
    <p class="lede" style="margin-inline:auto">This page doesn't exist. Maybe the link was mistyped, or the company hasn't been researched yet.</p>
    <p><a class="btn primary" href="/">${icon("back")} Back to the overview</a></p>
  </div>`);
  heroLines(view);
}
export { render_ as render };
