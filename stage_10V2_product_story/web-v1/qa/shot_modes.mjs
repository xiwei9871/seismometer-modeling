import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto('http://localhost:8941/?cb=' + Date.now(), { waitUntil: 'networkidle' });
await page.waitForFunction(() => window.__app?.store);
await page.waitForTimeout(1500);
await page.click('button:has-text("Acquisition")');
await page.waitForTimeout(2600);
await page.screenshot({ path: '/tmp/acq_inspect.png' });
// also the xray context beat — click a part then look inside
await page.evaluate(() => window.__app.store.set({mode:'architecture'}));
await page.waitForTimeout(200);
await page.click('button:has-text("Architecture")');
await page.waitForTimeout(2200);
await page.screenshot({ path: '/tmp/arch.png' });
// now zoom probe: any tilted mesh in architecture mode?
const tilted = await page.evaluate(() => {
  const THREE = window.__app.THREE; const out = [];
  window.__app.scene.traverse((o) => {
    if (!o.isMesh || !o.visible) return;
    const box = new THREE.Box3().setFromObject(o);
    const s = box.getSize(new THREE.Vector3());
    if (s.x < 0.04 || s.z < 0.04 || s.y > 0.1) return;
    const pos = o.geometry.getAttribute('position');
    const v = new THREE.Vector3(); const pts = [];
    for (let i = 0; i < pos.count; i += Math.max(1, Math.floor(pos.count/64))) {
      v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld); pts.push(v.clone());
    }
    const ys=pts.map(p=>p.y), xs=pts.map(p=>p.x), zs=pts.map(p=>p.z);
    const slope=(a,b)=>{const ma=a.reduce((p,c)=>p+c,0)/a.length,mb=b.reduce((p,c)=>p+c,0)/b.length;
      let n=0,d=0;for(let i=0;i<a.length;i++){n+=(a[i]-ma)*(b[i]-mb);d+=(a[i]-ma)**2;}return d?n/d:0;};
    const t = Math.hypot(slope(xs,ys), slope(zs,ys));
    if (t > 0.12) out.push({name:o.name, deg:+(Math.atan(t)*180/Math.PI).toFixed(1),
      size:s.toArray().map(x=>+(x*1000).toFixed(0)),
      center:box.getCenter(new THREE.Vector3()).toArray().map(x=>+(x*1000).toFixed(0))});
  });
  return out;
});
console.log(JSON.stringify(tilted, null, 0));
await browser.close();
