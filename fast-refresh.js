let fastRefreshBusy = false;

async function fastRefreshTick() {
  if (document.visibilityState !== 'visible' || fastRefreshBusy || typeof loadData !== 'function') return;
  fastRefreshBusy = true;
  try {
    await loadData();
  } finally {
    fastRefreshBusy = false;
  }
}

setInterval(fastRefreshTick, 15_000);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') fastRefreshTick();
});
