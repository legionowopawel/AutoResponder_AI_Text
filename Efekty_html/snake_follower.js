/**
 * =====================================================
 * EFEKT: Snake Follower (Wąż z kropek)
 * =====================================================
 * Klasyczny wąż złożony z kółek/kropek ciągnący się za kursorem.
 * Każdy segment goni poprzedni z opóźnieniem.
 * =====================================================
 */

window.EfektSnakeFollower = (function () {
  let canvas, ctx, animId;
  let mouseX, mouseY;
  let running = false;
  const COUNT = 24;
  const SPACING = 14;
  let dots = [];

  function init(options) {
    options = options || {};
    const color = options.color || '#7c3aed';
    const size = options.size || 10;

    canvas = document.getElementById('dragonCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    mouseX = window.innerWidth / 2;
    mouseY = window.innerHeight / 2;

    dots = [];
    for (let i = 0; i < COUNT; i++) {
      dots.push({ x: mouseX - i * SPACING, y: mouseY });
    }

    function onMouseMove(e) { mouseX = e.clientX; mouseY = e.clientY; }
    function onTouchMove(e) { mouseX = e.touches[0].clientX; mouseY = e.touches[0].clientY; }
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onTouchMove, { passive: true });

    function loop() {
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      dots[0].x += (mouseX - dots[0].x) * 0.25;
      dots[0].y += (mouseY - dots[0].y) * 0.25;

      for (let i = 1; i < COUNT; i++) {
        dots[i].x += (dots[i - 1].x - dots[i].x) * 0.3;
        dots[i].y += (dots[i - 1].y - dots[i].y) * 0.3;
      }

      for (let i = 0; i < COUNT; i++) {
        const t = i / COUNT;
        const radius = size * (1 - t * 0.6);
        const alpha = 1 - t * 0.5;
        ctx.beginPath();
        ctx.arc(dots[i].x, dots[i].y, radius, 0, Math.PI * 2);
        ctx.fillStyle = hexToRgba(color, alpha);
        ctx.fill();

        // Oczy na pierwszej kropce
        if (i === 0) {
          ctx.beginPath();
          ctx.arc(dots[i].x + 3, dots[i].y - 3, 2, 0, Math.PI * 2);
          ctx.fillStyle = '#fff';
          ctx.fill();
          ctx.beginPath();
          ctx.arc(dots[i].x + 3, dots[i].y - 3, 1, 0, Math.PI * 2);
          ctx.fillStyle = '#1a1a2e';
          ctx.fill();
        }
      }

      animId = requestAnimationFrame(loop);
    }

    running = true;
    loop();
  }

  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function destroy() {
    running = false;
    if (animId) cancelAnimationFrame(animId);
    if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  return { init, destroy };
})();
