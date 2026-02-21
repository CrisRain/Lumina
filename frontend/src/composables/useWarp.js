import { ref, computed, onUnmounted } from 'vue';
import axios from 'axios';

export function useWarp() {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

    // State
    const statusData = ref({
        status: 'disconnected',
        ip: '---',
        location: '---',
        city: 'Unknown',
        country: 'Unknown',
        details: {}
    });
    const isLoading = ref(false);
    const error = ref(null);
    const logs = ref([]);
    let socket = null;
    let reconnectTimeout = null;

    // Computed
    const isConnected = computed(() => statusData.value.status === 'connected');
    const ipAddress = computed(() => statusData.value.ip || statusData.value.details?.ip || 'Unknown');
    const city = computed(() => statusData.value.city || statusData.value.details?.city || 'Unknown');
    const country = computed(() => statusData.value.country || statusData.value.location || 'Unknown');
    const isp = computed(() => statusData.value.isp || statusData.value.details?.isp || 'Cloudflare WARP');
    const protocol = computed(() => statusData.value.warp_protocol || statusData.value.protocol || 'MASQUE');
    const proxyAddress = computed(() => statusData.value.proxy_address || 'socks5://127.0.0.1:1080');

    // API Helpers
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

    const toggleConnection = async () => {
        isLoading.value = true;
        if (isConnected.value) {
            await apiCall('post', '/disconnect');
        } else {
            await apiCall('post', '/connect');
        }
        setTimeout(() => { if (isLoading.value) isLoading.value = false; }, 2000);
    };

    const connectWebSocket = (onLogReceived = null) => {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/status`;

        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            apiCall('get', '/logs?limit=20').then(data => {
                if (data && data.logs) logs.value = data.logs;
            });
        };

        socket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (message.type === 'status') {
                statusData.value = message.data;
                if (isLoading.value && statusData.value.status === 'connected') isLoading.value = false;
            } else if (message.type === 'log') {
                logs.value.push(message.data);
                if (logs.value.length > 50) logs.value.shift();
                if (onLogReceived) onLogReceived();
            }
        };

        socket.onclose = () => {
            socket = null;
            reconnectTimeout = setTimeout(() => connectWebSocket(onLogReceived), 3000);
        };
    };

    onUnmounted(() => {
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        if (socket) socket.close();
    });

    return {
        statusData,
        isLoading,
        error,
        logs,
        isConnected,
        ipAddress,
        city,
        country,
        isp,
        protocol,
        proxyAddress,
        toggleConnection,
        connectWebSocket
    };
}
