/**
 * =====================================================
 * EFEKT: Fairy Dust / Stardust (Błyszczący pył)
 * =====================================================
 * Za kursorem sypią się błyszczące gwiazdki/iskierki.
 * Każda cząstka ma własną prędkość, grawitację i zanik.
 * =====================================================
 */

window.EfektFairyDust = (function () {
  let canvas, ctx, animId;
  let mouseX, mouseY;
  let running = false;
  let particles = [];
  let lastX, lastY;

  function init(options) {
    options = options || {};
    const colors = options.colors || ['#7c3aed', '#a855f7', '#ec4899', '#f59e0b', '#10b981', '#06b6d4'];
    const spawnRate = options.spawnRate || 4;
    const gravity = options.gravity || 0.08;

    canvas = document.getElementById('dragonCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    mouseX = window.innerWidth / 2;
    mouseY = window.innerHeight / 2;
    lastX = mouseX; lastY = mouseY;
    particles = [];

    function onMouseMove(e) {
      lastX = mouseX; lastY = mouseY;
      mouseX = e.clientX; mouseY = e.clientY;
      // Spawn cząstki przy ruchu myszy
      const dx = mouseX - lastX, dy = mouseY - lastY;
      const speed = Math.sqrt(dx * dx + dy * dy);
      const count = Math.min(Math.floor(speed / 3), spawnRate);
      for (let i = 0; i < count; i++) {
        spawnParticle(mouseX, mouseY, colors);
      }
    }

    function onTouchMove(e) {
      mouseX = e.touches[0].clientX; mouseY = e.touches[0].clientY;
      for (let i = 0; i < spawnRate; i++) spawnParticle(mouseX, mouseY, colors);
    }

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onTouchMove, { passive: true });

    function loop() {
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles = particles.filter(p => p.alpha > 0.01);

      particles.forEach(p => {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += gravity;
        p.alpha -= p.decay;
        p.rotation += p.rotSpeed;
        p.size *= 0.97;

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rotation);
        ctx.globalAlpha = p.alpha;

        if (p.shape === 'star') {
          drawStar(ctx, 0, 0, 4, p.size, p.size * 0.4);
          ctx.fillStyle = p.color;
          ctx.fill();
        } else if (p.shape === 'circle') {
          ctx.beginPath();
          ctx.arc(0, 0, p.size * 0.5, 0, Math.PI * 2);
          ctx.fillStyle = p.color;
          ctx.fill();
        } else {
          // Iskra - kreska
          ctx.strokeStyle = p.color;
          ctx.lineWidth = p.size * 0.3;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.moveTo(0, -p.size); ctx.lineTo(0, p.size);
          ctx.stroke();
        }
        ctx.restore();
      });

      animId = requestAnimationFrame(loop);
    }

    running = true;
    loop();
  }

  function spawnParticle(x, y, colors) {
    const shapes = ['star', 'circle', 'spark'];
    particles.push({
      x: x + (Math.random() - 0.5) * 10,
      y: y + (Math.random() - 0.5) * 10,
      vx: (Math.random() - 0.5) * 3,
      vy: (Math.random() - 0.5) * 3 - 1,
      color: colors[Math.floor(Math.random() * colors.length)],
      size: 3 + Math.random() * 6,
      alpha: 0.9 + Math.random() * 0.1,
      decay: 0.012 + Math.random() * 0.018,
      rotation: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.2,
      shape: shapes[Math.floor(Math.random() * shapes.length)]
    });
  }

  function drawStar(ctx, cx, cy, spikes, outerRadius, innerRadius) {
    let rot = (Math.PI / 2) * 3;
    const step = Math.PI / spikes;
    ctx.beginPath();
    ctx.moveTo(cx, cy - outerRadius);
    for (let i = 0; i < spikes; i++) {
      ctx.lineTo(cx + Math.cos(rot) * outerRadius, cy + Math.sin(rot) * outerRadius);
      rot += step;
      ctx.lineTo(cx + Math.cos(rot) * innerRadius, cy + Math.sin(rot) * innerRadius);
      rot += step;
    }
    ctx.lineTo(cx, cy - outerRadius);
    ctx.closePath();
  }

  function destroy() {
    running = false;
    if (animId) cancelAnimationFrame(animId);
    if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
    particles = [];
  }

  return { init, destroy };
})();
