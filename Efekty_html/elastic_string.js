/**
 * =====================================================
 * EFEKT: Elastic String (Gumka Recepturka)
 * =====================================================
 * Samotna linia zachowująca się jak gumka recepturka
 * przyczepiona do kursora myszy.
 * Punkt zaczepu jest elastycznie przyciągany do kursora.
 * =====================================================
 */

window.EfektElasticString = (function () {
  let canvas, ctx, animId;
  let mouseX, mouseY;
  let running = false;

  // Punkty siatki gumek
  let anchors = [];

  function init(options) {
    options = options || {};
    const color = options.color || '#7c3aed';
    const count = options.count || 8;

    canvas = document.getElementById('dragonCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    mouseX = window.innerWidth / 2;
    mouseY = window.innerHeight / 2;

    // Stwórz kilka punktów zaczepu rozmieszczonych na ekranie
    anchors = [];
    for (let i = 0; i < count; i++) {
      anchors.push({
        // Stały punkt zaczepienia (fixed)
        fx: (Math.random() * 0.8 + 0.1) * window.innerWidth,
        fy: (Math.random() * 0.8 + 0.1) * window.innerHeight,
        // Punkt kontrolny (porusza się elastycznie)
        cx: window.innerWidth / 2,
        cy: window.innerHeight / 2,
        cvx: 0, cvy: 0,
        color: shiftHue(color, i * 20),
        width: 1 + Math.random() * 2
      });
    }

    function onMouseMove(e) { mouseX = e.clientX; mouseY = e.clientY; }
    function onTouchMove(e) { mouseX = e.touches[0].clientX; mouseY = e.touches[0].clientY; }
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onTouchMove, { passive: true });

    function loop() {
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Kursor
      ctx.save();
      ctx.beginPath();
      ctx.arc(mouseX, mouseY, 5, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.restore();

      anchors.forEach(a => {
        // Punkt kontrolny elastycznie zmierza w stronę kursora
        const tx = (mouseX + a.fx) / 2;
        const ty = (mouseY + a.fy) / 2;
        const spring = 0.06;
        const damping = 0.82;

        a.cvx += (mouseX - a.cx) * spring;
        a.cvy += (mouseY - a.cy) * spring;
        a.cvx *= damping;
        a.cvy *= damping;
        a.cx += a.cvx;
        a.cy += a.cvy;

        // Rysuj elastyczną linię (krzywa Beziera)
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(a.fx, a.fy);
        ctx.quadraticCurveTo(a.cx, a.cy, mouseX, mouseY);
        ctx.strokeStyle = a.color;
        ctx.lineWidth = a.width;
        ctx.lineCap = 'round';
        ctx.shadowColor = a.color;
        ctx.shadowBlur = 3;
        ctx.globalAlpha = 0.7;
        ctx.stroke();
        ctx.restore();

        // Punkt zaczepu
        ctx.save();
        ctx.beginPath();
        ctx.arc(a.fx, a.fy, 3, 0, Math.PI * 2);
        ctx.fillStyle = a.color;
        ctx.globalAlpha = 0.8;
        ctx.fill();
        ctx.restore();
      });

      animId = requestAnimationFrame(loop);
    }

    running = true;
    loop();
  }

  function shiftHue(hex, degrees) {
    // Prosta zamiana koloru hex → lekko przesunięty odcień przez HSL
    try {
      const r = parseInt(hex.slice(1, 3), 16) / 255;
      const g = parseInt(hex.slice(3, 5), 16) / 255;
      const b = parseInt(hex.slice(5, 7), 16) / 255;
      const max = Math.max(r, g, b), min = Math.min(r, g, b);
      let h, s, l = (max + min) / 2;
      if (max === min) { h = s = 0; }
      else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
        else if (max === g) h = ((b - r) / d + 2) / 6;
        else h = ((r - g) / d + 4) / 6;
      }
      h = (h + degrees / 360) % 1;
      function hue2rgb(p, q, t) {
        if (t < 0) t += 1; if (t > 1) t -= 1;
        if (t < 1/6) return p + (q - p) * 6 * t;
        if (t < 1/2) return q;
        if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
        return p;
      }
      const q2 = l < 0.5 ? l * (1 + s) : l + s - l * s;
      const p2 = 2 * l - q2;
      const nr = Math.round(hue2rgb(p2, q2, h + 1/3) * 255);
      const ng = Math.round(hue2rgb(p2, q2, h) * 255);
      const nb = Math.round(hue2rgb(p2, q2, h - 1/3) * 255);
      return `rgb(${nr},${ng},${nb})`;
    } catch (e) { return hex; }
  }

  function destroy() {
    running = false;
    if (animId) cancelAnimationFrame(animId);
    if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
    anchors = [];
  }

  return { init, destroy };
})();
