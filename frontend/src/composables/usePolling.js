import { ref, computed, onUnmounted } from 'vue';
import axios from 'axios';

/**
 * Global polling-based state management.
 * Replaces WebSocket with simple HTTP polling for status and logs.
 * Singleton pattern: all components share the same reactive state.
 */

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

// ---- Shared singleton state ----
const statusData = ref({
    status: 'disconnected',
    ip: '---',
    location: '---',
    city: 'Unknown',
    country: 'Unknown',
    details: {}
});
const logs = ref([]);
const error = ref(null);

// Polling control
let statusTimer = null;
let logsTimer = null;
let activeConsumers = 0;

// Track last known log count for incremental fetch
let lastLogCount = 0;

// ---- API helper ----
const apiCall = async (method, url, data = null) => {
    try {
        const response = await axios[method](`${apiBaseUrl}${url}`, data);
        return response.data;
    } catch (err) {
        // Don't spam console on network errors during polling
        if (!err.message?.includes('Network Error')) {
            console.error(`API Error (${method} ${url}):`, err);
        }
        error.value = err;
        return null;
    }
};

// ---- Polling functions ----
const fetchStatus = async () => {
    const data = await apiCall('get', '/status');
    if (data) {
        statusData.value = data;
    }
};

const fetchLogs = async () => {
    const data = await apiCall('get', '/logs?limit=200');
    if (data && data.logs) {
        logs.value = data.logs;
    }
};

// ---- Polling lifecycle ----
const startPolling = () => {
    activeConsumers++;
    if (activeConsumers === 1) {
        // First consumer, start timers
        fetchStatus();
        fetchLogs();
        statusTimer = setInterval(fetchStatus, 3000);  // Poll status every 3s
        logsTimer = setInterval(fetchLogs, 4000);       // Poll logs every 4s
    }
};

const stopPolling = () => {
    activeConsumers = Math.max(0, activeConsumers - 1);
    if (activeConsumers === 0) {
        if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
        if (logsTimer) { clearInterval(logsTimer); logsTimer = null; }
    }
};

/**
 * Composable for components that need status data.
 * Automatically starts/stops polling based on component lifecycle.
 */
export function useStatus() {
    startPolling();
    onUnmounted(stopPolling);

    return {
        statusData,
        isConnected: computed(() => statusData.value.status === 'connected'),
        ipAddress: computed(() => statusData.value.ip || statusData.value.details?.ip || 'Unknown'),
        city: computed(() => statusData.value.city || statusData.value.details?.city || 'Unknown'),
        country: computed(() => statusData.value.country || statusData.value.location || 'Unknown'),
        isp: computed(() => statusData.value.isp || statusData.value.details?.isp || 'Cloudflare WARP'),
        protocol: computed(() => statusData.value.warp_protocol || statusData.value.protocol || 'MASQUE'),
        proxyAddress: computed(() => statusData.value.proxy_address || 'socks5://127.0.0.1:1080'),
        backend: computed(() => statusData.value.backend || 'usque'),
        warpMode: computed(() => statusData.value.warp_mode || 'proxy'),
        refreshStatus: fetchStatus,
    };
}

/**
 * Composable for components that need log data.
 */
export function useLogs() {
    startPolling();
    onUnmounted(stopPolling);

    return {
        logs,
        refreshLogs: fetchLogs,
    };
}

/**
 * Composable for WARP control actions (connect/disconnect/rotate).
 */
export function useWarpActions() {
    const isLoading = ref(false);

    const toggleConnection = async (isConnected) => {
        isLoading.value = true;
        if (isConnected) {
            await apiCall('post', '/disconnect');
        } else {
            await apiCall('post', '/connect');
        }
        // Wait a moment then refresh status
        setTimeout(async () => {
            await fetchStatus();
            isLoading.value = false;
        }, 2000);
    };

    const rotateIP = async () => {
        isLoading.value = true;
        await apiCall('post', '/rotate');
        setTimeout(async () => {
            await fetchStatus();
            isLoading.value = false;
        }, 1500);
    };

    return {
        isLoading,
        toggleConnection,
        rotateIP,
        apiCall,
    };
}
