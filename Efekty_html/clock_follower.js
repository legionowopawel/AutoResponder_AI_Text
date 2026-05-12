/**
 * =====================================================
 * EFEKT: Clock Follower (Zegar wokół kursora)
 * =====================================================
 * Aktualna godzina i data krążą wokół kursora myszy.
 * Kultowy gadżet z DHTML z przełomu XX/XXI wieku.
 * =====================================================
 */

window.EfektClockFollower = (function () {
  let canvas, ctx, animId;
  let mouseX, mouseY;
  let running = false;
  let orbitAngle = 0;

  function init(options) {
    options = options || {};
    const color = options.color || '#7c3aed';
    const radius = options.radius || 70;
    const speed = options.speed || 0.03;

    canvas = document.getElementById('dragonCanvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    mouseX = window.innerWidth / 2;
    mouseY = window.innerHeight / 2;

    function onMouseMove(e) { mouseX = e.clientX; mouseY = e.clientY; }
    function onTouchMove(e) { mouseX = e.touches[0].clientX; mouseY = e.touches[0].clientY; }
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onTouchMove, { passive: true });

    function getNow() {
      const now = new Date();
      const h = String(now.getHours()).padStart(2, '0');
      const m = String(now.getMinutes()).padStart(2, '0');
      const s = String(now.getSeconds()).padStart(2, '0');
      const d = String(now.getDate()).padStart(2, '0');
      const mo = String(now.getMonth() + 1).padStart(2, '0');
      const y = now.getFullYear();
      return { time: `${h}:${m}:${s}`, date: `${d}.${mo}.${y}` };
    }

    function drawRoundedRect(ctx, x, y, w, h, r) {
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + w - r, y);
      ctx.arcTo(x + w, y, x + w, y + r, r);
      ctx.lineTo(x + w, y + h - r);
      ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
      ctx.lineTo(x + r, y + h);
      ctx.arcTo(x, y + h, x, y + h - r, r);
      ctx.lineTo(x, y + r);
      ctx.arcTo(x, y, x + r, y, r);
      ctx.closePath();
    }

    function loop() {
      if (!running) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const { time, date } = getNow();

      // Kursor
      ctx.save();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(mouseX, mouseY, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Orbit linia (cienka, przezroczysta)
      ctx.save();
      ctx.strokeStyle = `${color}33`;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 6]);
      ctx.beginPath();
      ctx.arc(mouseX, mouseY, radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // Zegarek na orbicie
      const cx = mouseX + Math.cos(orbitAngle) * radius;
      const cy = mouseY + Math.sin(orbitAngle) * radius;

      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(orbitAngle + Math.PI / 2);

      // Tło zegarka
      const w = 80, h = 40;
      ctx.shadowColor = color;
      ctx.shadowBlur = 10;
      drawRoundedRect(ctx, -w / 2, -h / 2, w, h, 8);
      ctx.fillStyle = 'rgba(15,10,35,0.9)';
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Czas
      ctx.font = "bold 16px 'Ubuntu Mono', monospace";
      ctx.fillStyle = color;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(time, 0, -7);

      // Data
      ctx.font = "10px 'Ubuntu Mono', monospace";
      ctx.fillStyle = `${color}cc`;
      ctx.fillText(date, 0, 9);

      ctx.restore();

      // Data na przeciwnej stronie orbity
      const cx2 = mouseX + Math.cos(orbitAngle + Math.PI) * (radius * 0.6);
      const cy2 = mouseY + Math.sin(orbitAngle + Math.PI) * (radius * 0.6);

      ctx.save();
      ctx.translate(cx2, cy2);
      ctx.font = "bold 11px 'Ubuntu Mono', monospace";
      ctx.fillStyle = `${color}99`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('📅', 0, 0);
      ctx.restore();

      orbitAngle += speed;
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
