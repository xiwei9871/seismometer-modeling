import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto('http://localhost:8941/?cb=' + Date.now(), { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__app?.store);
await page.waitForTimeout(1500);
await page.click('button:has-text("Power")');
await page.waitForTimeout(5000);
await page.screenshot({ path: '/tmp/power_now.png' });
// zoom into one cell
await page.evaluate(() => {
  const { camera, cameraCtl } = window.__app;
  const cell = window.__app.registry.get('CELL_18650_01');
  const THREE = window.__app.THREE;
  const c = new THREE.Box3().setFromObject(cell.object3D).getCenter(new THREE.Vector3());
  camera.position.set(c.x + 0.09, c.y + 0.05, c.z + 0.12);
});
await page.waitForTimeout(600);
await page.screenshot({ path: '/tmp/cell_close.png' });
await browser.close();
