// Self-check: drives the product page through all five chapters and
// captures screenshots + runtime semantic state.
// Usage:  node qa/flow_check.mjs [outdir]
import { chromium } from 'playwright';

const OUT = process.argv[2] || '/tmp/flow';
const URL = 'http://localhost:8941/?nocache=' + Date.now();

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on('pageerror', (e) => errors.push('PAGE: ' + e.message.slice(0, 160)));
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text().slice(0, 160));
});

await page.goto(URL);
await page.waitForFunction(() => window.__app && window.__app.store.get().ready, null, { timeout: 30000 });
await page.waitForTimeout(3000);

const rail = async (label, shot) => {
  await page.evaluate((l) => {
    [...document.querySelectorAll('.rail-btn')]
      .find((b) => b.textContent.includes(l))?.click();
  }, label);
  await page.waitForTimeout(4500);
  await page.screenshot({ path: `${OUT}_${shot}.png` });
  return page.evaluate(() => {
    const s = window.__app.store.get();
    return { mode: s.mode, sys: s.focusedSystem };
  });
};

const entityInfo = (ids) =>
  page.evaluate((ids) => {
    const app = window.__app;
    const v = new app.THREE.Vector3();
    const out = {};
    for (const id of ids) {
      const e = app.registry.get(id);
      if (!e) { out[id] = null; continue; }
      e.object3D.getWorldPosition(v);
      let minOp = 1;
      e.object3D.traverse((o) => {
        if (o.isMesh && o.material && o.material.opacity !== undefined)
          minOp = Math.min(minOp, o.material.opacity);
      });
      out[id] = { pos: v.toArray().map((x) => +x.toFixed(3)), minOp: +minOp.toFixed(2), vis: e.object3D.visible };
    }
    return out;
  }, ids);

const report = { errors };

// overview must stay look-only: click + dblclick on the device
await page.mouse.click(660, 420);
await page.mouse.dblclick(660, 420);
await page.waitForTimeout(800);
report.overviewAfterClicks = await page.evaluate(() => window.__app.store.get().mode);
await page.screenshot({ path: `${OUT}_overview.png` });

report.architecture = await rail('Architecture', 'arch');
report.sensing = await rail('Sensing', 'sensing');
report.acquisition = await rail('Acquisition', 'acq');
report.acquisitionBoards = await entityInfo(['PCB_A', 'PCB_B', 'PART_019', 'PART_006', 'PART_007']);
report.power = await rail('Power', 'power');
report.transmission = await rail('Transmission', 'trans');
report.transmissionAntenna = await entityInfo(['WIFI_ANTENNA']);
report.powerCells = await entityInfo(
  Array.from({ length: 6 }, (_, i) => `CELL_18650_0${i + 1}`)
);
report.backToOverview = await rail('Overview', 'back');

console.log(JSON.stringify(report, null, 1));
await browser.close();
