/**
 * =====================================================
 * EFEKT: Text Circle / Spinning Text (Wirujący napis)
 * =====================================================
 * Tekst (litera po literze) krąży po okręgu wokół kursora
 * jak satelita — kultowy efekt z lat 90./00.
 * =====================================================
 */

window.EfektTextCircle = (function () {
  let canvas, ctx, animId;
  let mouseX, mouseY;
  let running = false;
  let angle = 0;

  function init(options) {
    options = options || {};
    const text = options.text || '✦ PAWEŁ W ✦ CV 2026 ✦ WARSZAWA ✦ ANALIZA DANYCH ✦';
    const radius = options.radius || 80;
    const speed = options.speed || 0.025;
    const color = options.color || '#7c3aed';
    const fontSize = options.fontSize || 13;

    canvas = document.getElementById('dragonCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    mouseX = window.innerWidth / 2;
    mouseY = window.innerHeight / 2;

    function onMouseMove(e) { mouseX = e.clientX; mouseY = e.clientY; }
    function onTouchMove(e) { mouseX = e.touches[0].clientX; mouseY = e.touches[0].clientY; }
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onTouchMove, { passive: true });

    const chars = text.split('');
    const angleStep = (Math.PI * 2) / chars.length;

    function loop() {
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Kursor — fioletowy krzyżyk
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(mouseX - 6, mouseY); ctx.lineTo(mouseX + 6, mouseY); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(mouseX, mouseY - 6); ctx.lineTo(mouseX, mouseY + 6); ctx.stroke();
      ctx.restore();

      ctx.font = `bold ${fontSize}px 'Ubuntu Mono', monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      chars.forEach((char, i) => {
        const a = angle + i * angleStep;
        const x = mouseX + Math.cos(a) * radius;
        const y = mouseY + Math.sin(a) * radius;
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(a + Math.PI / 2);
        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 4;
        ctx.fillText(char, 0, 0);
        ctx.restore();
      });

      angle += speed;
      animId = requestAnimationFrame(loop);
    }

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
