document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const statusContent = document.getElementById('status-content');

    const fetchStatus = async () => {
        try {
            const response = await fetch('/status');
            const status = await response.json();
            statusContent.textContent = JSON.stringify(status, null, 2);
        } catch (error) {
            statusContent.textContent = 'Error fetching status.';
        }
    };

    startBtn.addEventListener('click', async () => {
        await fetch('/start', { method: 'POST' });
        fetchStatus();
    });

    stopBtn.addEventListener('click', async () => {
        await fetch('/stop', { method: 'POST' });
        fetchStatus();
    });

    // Fetch status every 5 seconds
    setInterval(fetchStatus, 5000);
    fetchStatus();
});
