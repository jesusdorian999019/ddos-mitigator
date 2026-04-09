// Dashboard en tiempo real para DDoS Mitigator
// WebSocket nativo + API REST + Chart.js

let ppsChart;
let alertasCount = 0;
let bloqueadasCount = 0;
let ws = null;
let wsReconnectInterval = 3000;
let messageSequence = 0;

// Inicializar Chart.js
function initChart() {
    const ctx = document.getElementById('ppsChart');
    if (!ctx) {
        console.warn('Canvas ppsChart no encontrado');
        return;
    }
    const ctxContext = ctx.getContext('2d');
    ppsChart = new Chart(ctxContext, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'PPS por IP (últimas 20)',
                data: [],
                borderColor: '#00d4ff',
                backgroundColor: 'rgba(0, 212, 255, 0.3)',
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#ffffff' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                },
                x: {
                    ticks: { color: '#ffffff' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                }
            },
            plugins: {
                legend: {
                    labels: { color: '#ffffff' }
                }
            }
        }
    });
}

// Actualizar métricas
function updateMetrics(stats) {
    if (!stats) return;
    
    // Contadores
    const alertasEl = document.getElementById('alertas-count');
    const bloqueadasEl = document.getElementById('bloqueadas-count');
    if (alertasEl) alertasEl.textContent = stats.alertas || 0;
    if (bloqueadasEl) bloqueadasEl.textContent = stats.bloqueadas_count || 0;
    
    // Gráfico
    if (stats.top_ips && stats.top_ips.length > 0) {
        const labels = stats.top_ips.map(ipData => {
            const ip = ipData.ip || '';
            return ip.length > 12 ? ip.slice(-12) : ip;
        });
        const data = stats.top_ips.map(ipData => ipData.pps || 0);
        
        if (ppsChart) {
            ppsChart.data.labels = labels;
            ppsChart.data.datasets[0].data = data;
            ppsChart.update('none');
        }
    }
    
    // Top IPs
    updateTopIPs(stats.top_ips);
    
    // Alertas
    updateAlertas(stats.alertas_detalle);
    
    // Logs enriquecidos
    if (stats.logs_enriquecidos && stats.logs_enriquecidos.length > 0) {
        updateLogsEnriquecidos(stats.logs_enriquecidos);
    }
}

// Top IPs tabla
function updateTopIPs(topIPs) {
    const container = document.getElementById('top-ips');
    if (!container) return;
    
    if (!topIPs || topIPs.length === 0) {
        container.innerHTML = '<p style=\"padding: 10px;\">Sin datos</p>';
        return;
    }
    
    container.innerHTML = topIPs.slice(0, 15).map((ipData, idx) => {
        const ip = ipData.ip || 'N/A';
        const pps = ipData.pps || 0;
        const proto = ipData.proto || 'OTRO';
        return `<div class=\"ip-item\" style=\"animation: slideIn 0.3s ease-out ${idx * 0.05}s both;\">
            <div style=\"flex: 1;\">
                <strong>${escapeHtml(ip)}</strong><br>
                <small>${pps} PPS (${proto})</small>
            </div>
            <span class=\"status-rojo\">${pps > 1000 ? '🔴 CRÍTICO' : '🟠 ALTO'}</span>
        </div>`;
    }).join('');
}

// Alertas detalle
function updateAlertas(alertas) {
    const container = document.getElementById('alertas-detalle');
    if (!container) return;
    
    if (!alertas || alertas.length === 0) {
        container.innerHTML = '<p style=\"padding: 10px;\">Sin alertas</p>';
        return;
    }
    
    container.innerHTML = alertas.map((alerta, idx) => {
        const ip = alerta.ip || 'N/A';
        const razon = alerta.razon || 'Desconocida';
        const pps = alerta.pps || 0;
        const time = alerta.timestamp ? alerta.timestamp.slice(11, 19) : 'N/A';
        return `<div class=\"alerta-item\" style=\"animation: slideIn 0.3s ease-out ${idx * 0.05}s both;\">
            <div>
                <strong>${escapeHtml(ip)}</strong> - ${escapeHtml(razon)}<br>
                <small>PPS: ${pps} | ${time}</small>
            </div>
            <span class=\"status-rojo\">ALERTA</span>
        </div>`;
    }).join('');
}

// Logs enriquecidos
function updateLogsEnriquecidos(logs) {
    let container = document.getElementById('logs-enriquecidos');
    if (!container) {
        const dashboard = document.querySelector('.dashboard');
        if (!dashboard) return;
        container = document.createElement('div');
        container.id = 'logs-enriquecidos';
        container.innerHTML = '<h3>🌍 Logs Forenses Enriquecidos</h3>';
        dashboard.appendChild(container);
    }
    
    if (!logs || logs.length === 0) {
        container.innerHTML = '<h3>🌍 Logs Forenses Enriquecidos</h3><p style=\"padding: 10px;\">Sin logs</p>';
        return;
    }
    
    const logsHtml = logs.slice(0, 10).map((log, idx) => {
        const ip = log.ip || 'N/A';
        const pais = log.pais || 'Desconocido';
        const ciudad = log.ciudad || '';
        const asn = log.asn || 'N/A';
        const tipo = log.tipo_ataque || 'N/A';
        const pps = log.pps || 0;
        const time = log.timestamp ? log.timestamp.slice(11, 19) : 'N/A';
        return `<div class=\"log-item\" style=\"animation: slideIn 0.3s ease-out ${idx * 0.05}s both;\">
            <div style=\"flex: 1;\">
                <strong>${escapeHtml(ip)}</strong> (${escapeHtml(pais)}, ${escapeHtml(ciudad)})<br>
                <small>${escapeHtml(tipo)} | ${pps} PPS | ${escapeHtml(asn)}</small>
            </div>
            <span>${time}</span>
        </div>`;
    }).join('');
    
    container.innerHTML = '<h3>🌍 Logs Forenses Enriquecidos</h3>' + logsHtml;
}

// Utils
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// WebSocket connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws`;
    
    try {
        ws = new WebSocket(url);
        
        ws.onopen = () => {
            console.log('✅ WebSocket conectado');
            document.body.classList.remove('ws-disconnected');
            document.body.classList.add('ws-connected');
            wsReconnectInterval = 3000;
            
            // Keep-alive
            setInterval(() => {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'ping', seq: messageSequence++ }));
                }
            }, 30000);
        };
        
        ws.onmessage = (event) => {
            try {
                let data = event.data;
                if (typeof data === 'string') {
                    data = JSON.parse(data);
                }
                updateMetrics(data);
            } catch (e) {
                console.warn('Error parseando WS:', e);
            }
        };
        
        ws.onerror = (error) => {
            console.error('❌ Error WebSocket:', error);
            document.body.classList.add('ws-disconnected');
        };
        
        ws.onclose = () => {
            console.warn('⚠️ WebSocket cerrado');
            document.body.classList.add('ws-disconnected');
            // Reconectar
            setTimeout(connectWebSocket, wsReconnectInterval);
            wsReconnectInterval = Math.min(wsReconnectInterval * 1.5, 30000);
        };
    } catch (e) {
        console.error('Error conectando WebSocket:', e);
        setTimeout(connectWebSocket, 5000);
    }
}

// Fetch APIs
function fetchStats() {
    fetch('/stats')
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            if (data.top_ips) {
                updateMetrics(data);
            }
        })
        .catch(err => console.debug('Error fetch stats:', err));
}

// Actualizar datos vía REST si WebSocket no está disponible
setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        fetchStats();
    }
}, 5000);

// Inicializar
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Inicializando dashboard');
    initChart();
    
    // Estilos para animaciónes
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateX(-10px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }
        body.ws-disconnected::before {
            content: '⚠️ Sin conexión en tiempo real';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: #f87171;
            color: white;
            padding: 10px;
            font-weight: bold;
            z-index: 9999;
        }
    `;
    document.head.appendChild(style);
    
    connectWebSocket();
    fetchStats();
});
