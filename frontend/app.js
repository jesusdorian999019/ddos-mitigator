// JavaScript para panel realtime DDoS Mitigator
const socket = io();

let ppsChart;
let alertasCount = 0;
let bloqueadasCount = 0;

// Inicializar Chart.js
function initChart() {
    const ctx = document.getElementById('ppsChart').getContext('2d');
    ppsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'PPS por IP',
                data: [],
                borderColor: '#00d4ff',
                backgroundColor: 'rgba(0, 212, 255, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true }
            },
            plugins: { legend: { labels: { color: '#ffffff' } } }
        }
    });
}

// Actualizar métricas
function updateMetrics(stats) {
    if (!stats) return;
    
    // Actualizar contadores
    const alertasEl = document.getElementById('alertas-count');
    const bloqueadasEl = document.getElementById('bloqueadas-count');
    if (alertasEl) alertasEl.textContent = stats.alertas || 0;
    if (bloqueadasEl) bloqueadasEl.textContent = stats.bloqueadas_count || 0;
    
    // Actualizar gráfico
    if (stats.top_ips) {
        const labels = stats.top_ips.map(ipData => ipData.ip.slice(-15));
        const data = stats.top_ips.map(ipData => ipData.pps);
        ppsChart.data.labels = labels;
        ppsChart.data.datasets[0].data = data;
        ppsChart.update('none');
    }
    
    // Top IPs
    updateTopIPs(stats.top_ips);
    
    // Alertas detalle
    updateAlertas(stats.alertas_detalle);
}

// Top IPs tabla
function updateTopIPs(topIPs) {
    const container = document.getElementById('top-ips');
    if (!topIPs || topIPs.length === 0) {
        container.innerHTML = '<p>Sin datos</p>';
        return;
    }
    
    container.innerHTML = topIPs.map(ipData => 
        `<div class="ip-item">
            <span>${ipData.ip}</span>
            <span>${ipData.pps} PPS</span>
            <span class="status-verde">${ipData.proto}</span>
        </div>`
    ).join('');
}

// Alertas detalle
function updateAlertas(alertas) {
    const container = document.getElementById('alertas-detalle');
    if (!alertas || alertas.length === 0) {
        container.innerHTML = '<p>Sin alertas</p>';
        return;
    }
    
    container.innerHTML = alertas.map(alerta => 
        `<div class="alerta-item">
            <div>
                <strong>${alerta.ip}</strong> - ${alerta.razon}</br>
                <small>PPS: ${alerta.pps} | ${alerta.timestamp}</small>
            </div>
            <span class="status-rojo">BLOQUEADA</span>
        </div>`
    ).join('');
}

function updateLogsEnriquecidos(logs) {
    const container = document.getElementById('logs-enriquecidos') || createLogsContainer();
    if (!logs || logs.length === 0) {
        container.innerHTML = '<p>Sin logs enriquecidos</p>';
        return;
    }
    
    container.innerHTML = logs.map(log => 
        `<div class="log-item">
            <div>
                <strong>${log.ip}</strong> (${log.pais}, ${log.asn})</br>
                <small>${log.tipo_ataque} | ${log.pps} PPS | ${log.hostname}</small>
            </div>
            <span class="status-rojo">${log.timestamp.slice(11,19)}</span>
        </div>`
    ).join('');
}

function createLogsContainer() {
    const dashboard = document.querySelector('.dashboard');
    const logsDiv = document.createElement('div');
    logsDiv.id = 'logs-enriquecidos';
    logsDiv.innerHTML = '<h3>Logs Forenses Enriquecidos</h3>';
    dashboard.appendChild(logsDiv);
    return logsDiv;
}

// Socket.io eventos
socket.on('connect', () => {
    console.log('Conectado al servidor WebSocket');
});

socket.on('disconnect', () => {
    console.log('Desconectado');
});

// Recibir stats realtime (intentar ambos eventos)
socket.on('message', (data) => {
    if (typeof data === 'string') {
        try {
            data = JSON.parse(data);
        } catch (e) {
            console.warn('No se pudo parsear mensaje:', e);
            return;
        }
    }
    updateMetrics(data);
});

socket.on('data', (data) => {
    if (typeof data === 'string') {
        try {
            data = JSON.parse(data);
        } catch (e) {
            console.warn('No se pudo parsear data:', e);
            return;
        }
    }
    updateMetrics(data);
});

socket.on('connect_error', (error) => {
    console.error('Error de conexión WebSocket:', error);
});

// Reconexión automática
socket.on('disconnect', () => {
    console.log('Desconectado - reconectando...');
    setTimeout(() => socket.connect(), 3000);
});

// Inicializar
initChart();
updateMetrics({});  // Valores iniciales

// Fetch inicial
fetch('/estadisticas')
    .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    })
    .then(updateMetrics)
    .catch(err => console.error('Error en fetch inicial:', err));

// Actualizar logs enriquecidos cuando broadcast incluye datos
const originalBroadcast = socket.on;
setInterval(() => {
    fetch('/alertas')
        .then(res => res.json())
        .then(data => {
            if (data.alertas && data.alertas.length > 0) {
                updateLogsEnriquecidos(data.alertas.slice(0, 5));
            }
        })
        .catch(err => console.debug('Error fetch alertas:', err));
}, 5000);
