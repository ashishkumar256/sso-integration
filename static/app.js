const uptimeNode = document.querySelector("[data-uptime]");

if (uptimeNode) {
  const startedAt = Date.now();
  const initialUptime = Number(uptimeNode.dataset.uptime || 0);

  window.setInterval(() => {
    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    uptimeNode.textContent = String(initialUptime + elapsed);
  }, 1000);
}