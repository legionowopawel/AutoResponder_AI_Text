/**
 * =====================================================
 * EFEKT: Elastic Dragon (Smok)
 * =====================================================
 * Klasyczny smok ciągnący się za kursorem myszy.
 * Zbudowany z głowy i segmentów tułowia rysowanych na canvas.
 * =====================================================
 */

window.EfektElasticDragon = (function () {
  let canvas, ctx, animId;
  let mouseX, mouseY;
  const SEGMENTS = 28;
  const SEG_LEN = 18;
  let dragon = [];
  let running = false;

  function init(options) {
    options = options || {};
    const color1 = options.color1 || '#7c3aed';
    const color2 = options.color2 || '#a855f7';

    canvas = document.getElementById('dragonCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    mouseX = window.innerWidth / 2;
    mouseY = window.innerHeight / 2;

    dragon = [];
    for (let i = 0; i < SEGMENTS; i++) {
      dragon.push({ x: mouseX - i * SEG_LEN, y: mouseY });
    }

    function onMouseMove(e) { mouseX = e.clientX; mouseY = e.clientY; }
    function onTouchMove(e) { mouseX = e.touches[0].clientX; mouseY = e.touches[0].clientY; }
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onTouchMove, { passive: true });

    function update() {
      dragon[0].x += (mouseX - dragon[0].x) * 0.22;
      dragon[0].y += (mouseY - dragon[0].y) * 0.22;
      for (let i = 1; i < SEGMENTS; i++) {
        const prev = dragon[i - 1], curr = dragon[i];
        const dx = curr.x - prev.x, dy = curr.y - prev.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > SEG_LEN) { const r = SEG_LEN / dist; curr.x = prev.x + dx * r; curr.y = prev.y + dy * r; }
      }
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const r1 = 124, g1 = 58, b1 = 237;
      const r2 = 168, g2 = 85, b2 = 247;

      for (let i = 0; i < SEGMENTS - 1; i++) {
        const t = i / SEGMENTS;
        const seg = dragon[i], next = dragon[i + 1];
        const w = (1 - t) * 11 + 2;
        const r = Math.round(r1 + (r2 - r1) * t);
        const g = Math.round(g1 + (g2 - g1) * t);
        const b = Math.round(b1 + (b2 - b1) * t);
        ctx.beginPath(); ctx.moveTo(seg.x, seg.y); ctx.lineTo(next.x, next.y);
        ctx.strokeStyle = `rgba(${r},${g},${b},0.85)`; ctx.lineWidth = w; ctx.lineCap = 'round'; ctx.stroke();
        if (i % 2 === 0 && i > 2) {
          const dx = next.x - seg.x, dy = next.y - seg.y;
          const px = -dy / SEG_LEN * (w * 0.7), py = dx / SEG_LEN * (w * 0.7);
          const mx = (seg.x + next.x) / 2, my = (seg.y + next.y) / 2;
          ctx.beginPath(); ctx.arc(mx + px * 0.5, my + py * 0.5, w * 0.3, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${r},${g},${b},0.4)`; ctx.fill();
        }
      }

      const head = dragon[0], neck = dragon[1];
      const headAngle = Math.atan2(head.y - neck.y, head.x - neck.x);
      const grd = ctx.createRadialGradient(head.x, head.y, 0, head.x, head.y, 20);
      grd.addColorStop(0, 'rgba(124,58,237,0.25)'); grd.addColorStop(1, 'rgba(124,58,237,0)');
      ctx.beginPath(); ctx.arc(head.x, head.y, 20, 0, Math.PI * 2); ctx.fillStyle = grd; ctx.fill();

      ctx.save(); ctx.translate(head.x, head.y); ctx.rotate(headAngle);
      ctx.beginPath(); ctx.ellipse(6, 0, 12, 8, 0, 0, Math.PI * 2);
      ctx.fillStyle = color1; ctx.fill(); ctx.strokeStyle = '#5b21b6'; ctx.lineWidth = 1; ctx.stroke();
      ctx.beginPath(); ctx.arc(8, -5, 3.5, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill();
      ctx.beginPath(); ctx.arc(8, -5, 2, 0, Math.PI * 2); ctx.fillStyle = '#1a1a2e'; ctx.fill();
      ctx.beginPath(); ctx.arc(9, -6, 0.8, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill();
      ctx.beginPath(); ctx.arc(16, -2, 1.2, 0, Math.PI * 2); ctx.fillStyle = '#5b21b6'; ctx.fill();
      ctx.beginPath(); ctx.moveTo(4, -8); ctx.lineTo(2, -16); ctx.lineTo(7, -8); ctx.fillStyle = color2; ctx.fill();
      ctx.beginPath(); ctx.moveTo(-2, -7); ctx.quadraticCurveTo(-8, -14, -4, -18); ctx.quadraticCurveTo(-1, -12, 2, -7);
      ctx.fillStyle = 'rgba(168,85,247,0.6)'; ctx.fill(); ctx.restore();

      const tail = dragon[SEGMENTS - 1], pre = dragon[SEGMENTS - 2];
      const tailAngle = Math.atan2(tail.y - pre.y, tail.x - pre.x);
      ctx.save(); ctx.translate(tail.x, tail.y); ctx.rotate(tailAngle);
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.quadraticCurveTo(8, -6, 14, -2);
      ctx.quadraticCurveTo(8, 0, 6, 4); ctx.quadraticCurveTo(12, 2, 16, 4);
      ctx.strokeStyle = 'rgba(168,85,247,0.7)'; ctx.lineWidth = 2; ctx.stroke(); ctx.restore();
    }

    function loop() { if (!running) return; update(); draw(); animId = requestAnimationFrame(loop); }
    running = true;
    loop();
  }

  function destroy() {
    running = false;
    if (animId) cancelAnimationFrame(animId);
    if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  return { init, destroy };
})();
