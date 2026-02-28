import { ref, computed } from 'vue';
import axios from 'axios';

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

// Global Singleton State
const statusData = ref({
    status: 'disconnected',
    ip: '---',
    location: '---',
    city: 'Unknown',
    country: 'Unknown',
    details: {},
    backend: 'usque',
    warp_protocol: 'MASQUE',
    warp_mode: 'proxy',
    is_docker: false
});

const logs = ref([]);
const isLoading = ref(false);
const error = ref(null);
let lastLogId = 0;

// WebSocket Logic
let socket = null;
let reconnectTimeout = null;
let isInitialized = false;

const apiCall = async (method, url, data = null) => {
    try {
        const response = await axios[method](`${apiBaseUrl}${url}`, data);
        return response.data;
    } catch (err) {
        console.error(`API Error (${method} ${url}):`, err);
        error.value = err;
        return null;
    }
};

const appendLogs = (entries = []) => {
    if (!Array.isArray(entries) || entries.length === 0) return;
    for (const entry of entries) {
        if (!entry || typeof entry.id !== 'number') continue;
        if (entry.id <= lastLogId) continue;
        logs.value.push(entry);
        lastLogId = entry.id;
    }
    if (logs.value.length > 300) {
        logs.value = logs.value.slice(-300);
    }
};

const connectWebSocket = () => {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    
    let wsHost = window.location.host;
    // Handle dev environment where API might be on a different port if not proxied
    if (apiBaseUrl.startsWith('http')) {
        try {
            const url = new URL(apiBaseUrl);
            wsHost = url.host;
        } catch (e) {
            console.warn('Invalid API Base URL, using window.location.host');
        }
    }

    // Determine path based on environment
    // In production (served by FastAPI), /ws/status is correct
    // In dev (Vite), we might need to proxy /ws to backend
    const token = localStorage.getItem('auth_token');
    const qs = token ? `?token=${encodeURIComponent(token)}` : '';
    const wsUrl = `${wsProtocol}//${wsHost}/ws/status${qs}`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        // Initial pull once per websocket connection, then rely on ws incremental logs.
        apiCall('get', `/logs?limit=50&since_id=${lastLogId}`).then(data => {
            if (data && data.logs) {
                appendLogs(data.logs);
                if (typeof data.latest_id === 'number' && data.latest_id > lastLogId) {
                    lastLogId = data.latest_id;
                }
            }
        });
    };

    socket.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            if (message.type === 'status') {
                statusData.value = { ...statusData.value, ...message.data };
                if (isLoading.value && statusData.value.status === 'connected') {
                     isLoading.value = false;
                }
            } else if (message.type === 'log') {
                appendLogs([message.data]);
            }
        } catch (e) {
            console.error('Error parsing WS message:', e);
        }
    };

    socket.onclose = () => {
        socket = null;
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        reconnectTimeout = setTimeout(connectWebSocket, 3000);
    };
    
    socket.onerror = (err) => {
        console.error('WebSocket error:', err);
        // Let onclose handle reconnection
    };
};

// Initialize once
const init = () => {
    if (!isInitialized) {
        connectWebSocket();
        isInitialized = true;
    }
};

// Composables
export function useStatus() {
    init(); // Ensure connection is started
    
    return {
        statusData,
        backend: computed(() => statusData.value.backend || 'usque'),
        protocol: computed(() => statusData.value.warp_protocol || 'MASQUE'),
        warpMode: computed(() => statusData.value.warp_mode || 'proxy'),
        isConnected: computed(() => statusData.value.status === 'connected'),
        ipAddress: computed(() => statusData.value.ip || statusData.value.details?.ip || 'Unknown'),
        city: computed(() => statusData.value.city || statusData.value.details?.city || 'Unknown'),
        country: computed(() => statusData.value.country || statusData.value.location || 'Unknown'),
        isp: computed(() => statusData.value.isp || statusData.value.details?.isp || 'Cloudflare WARP'),
        proxyAddress: computed(() => statusData.value.proxy_address || 'socks5://127.0.0.1:1080'),
    };
}

export function useLogs() {
    init();
    return { logs };
}

export function useWarpActions() {
    init();
    
    const toggleConnection = async () => {
        isLoading.value = true;
        const isConnected = statusData.value.status === 'connected';
        
        if (isConnected) {
            await apiCall('post', '/disconnect');
        } else {
            await apiCall('post', '/connect');
        }
        
        // Fallback timeout
        setTimeout(() => { 
            if (isLoading.value) isLoading.value = false; 
        }, 5000);
    };

    return {
        isLoading,
        apiCall,
        toggleConnection
    };
}
