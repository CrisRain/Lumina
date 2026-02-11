<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-2xl font-bold text-gray-900">Settings</h2>
      <p class="text-sm text-gray-500">Configure connection parameters and preferences</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      
      <!-- Connection Settings -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 md:col-span-2">
        <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
          <GlobeAltIcon class="w-5 h-5 text-orange-500" />
          Connection Endpoint
        </h3>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Custom Endpoint Address</label>
            <p class="text-xs text-gray-500 mb-3">Override the default Cloudflare endpoint (e.g. for better latency).</p>
            
            <div class="relative flex items-center">
              <input 
                v-model="customEndpoint" 
                type="text" 
                placeholder="162.159.192.1:2408" 
                class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-100 outline-none transition-all font-mono text-sm"
                @keyup.enter="setEndpoint"
                :disabled="isProcessing"
              />
              <button 
                @click="setEndpoint"
                :disabled="isProcessing"
                class="absolute right-1.5 px-3 py-1.5 rounded-lg bg-orange-600 hover:bg-orange-700 text-white text-xs font-bold transition-all disabled:opacity-50"
              >
                {{ isProcessing ? 'SAVING...' : 'APPLY' }}
              </button>
            </div>
            <p class="text-[10px] text-gray-400 mt-2">Leave empty to use default. Applying changes will reconnect.</p>
          </div>
        </div>
      </div>

      <!-- Port Configuration -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 md:col-span-2">
        <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
          <ServerStackIcon class="w-5 h-5 text-violet-500" />
          Port Configuration
        </h3>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <!-- SOCKS5 Port -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">SOCKS5 Proxy Port</label>
            <p class="text-xs text-gray-500 mb-3">Port for SOCKS5 proxy connections. Default: 1080.</p>
            <div class="relative flex items-center">
              <input 
                v-model.number="socks5Port" 
                type="number" 
                min="1" max="65535"
                placeholder="1080" 
                class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-violet-500 focus:ring-2 focus:ring-violet-100 outline-none transition-all font-mono text-sm"
                @keyup.enter="savePorts"
                :disabled="isProcessing"
              />
            </div>
          </div>

          <!-- Panel Port -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Panel Port</label>
            <p class="text-xs text-gray-500 mb-3">Port for Web UI and API. Default: 8000.</p>
            <div class="relative flex items-center">
              <input 
                v-model.number="panelPort" 
                type="number" 
                min="1" max="65535"
                placeholder="8000" 
                class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-violet-500 focus:ring-2 focus:ring-violet-100 outline-none transition-all font-mono text-sm"
                @keyup.enter="savePorts"
                :disabled="isProcessing"
              />
            </div>
          </div>
        </div>

        <div class="mt-4 flex items-center justify-between">
          <p class="text-[10px] text-gray-400">
            SOCKS5 port changes take effect after reconnect. Panel port changes require a service restart.
          </p>
          <button 
            @click="savePorts"
            :disabled="isProcessing || (!portsChanged)"
            class="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ isProcessing ? 'SAVING...' : 'SAVE PORTS' }}
          </button>
        </div>

        <!-- Restart warning -->
        <div v-if="restartRequired" class="mt-3 p-3 bg-amber-50 rounded-xl border border-amber-200">
          <p class="text-xs text-amber-700 flex items-center gap-1.5">
            <ExclamationTriangleIcon class="w-4 h-4 flex-shrink-0" />
            Panel port changed. Please restart the service for changes to take effect.
          </p>
        </div>
      </div>

      <!-- Protocol Settings -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
        <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
          <ShieldCheckIcon class="w-5 h-5 text-emerald-500" />
          Protocol Selection
        </h3>
        
        <div class="space-y-4">
          <div class="p-4 rounded-xl border" :class="canSwitchProtocol ? 'bg-indigo-50 border-indigo-100' : 'bg-gray-50 border-gray-100'">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm font-medium text-gray-900">Transport Protocol</span>
              <span class="text-xs font-mono px-2 py-0.5 rounded bg-white border border-gray-200">{{ currentProtocol }}</span>
            </div>
            
            <p class="text-xs text-gray-500 mb-4">
              Choose between MASQUE (modern, robust) and WireGuard (legacy, faster in some cases).
              <span v-if="!canSwitchProtocol" class="block mt-1 text-orange-600 font-medium">Only available in Official Backend + TUN Mode.</span>
            </p>

            <button 
              v-if="canSwitchProtocol"
              @click="toggleProtocol"
              :disabled="isProcessing"
              class="w-full py-2 px-4 rounded-lg bg-white border border-indigo-200 text-indigo-700 text-sm font-medium hover:bg-indigo-50 transition-colors shadow-sm"
            >
              Switch to {{ currentProtocol === 'MASQUE' ? 'WireGuard' : 'MASQUE' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Advanced Actions -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 md:col-span-2">
        <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
          <WrenchScrewdriverIcon class="w-5 h-5 text-gray-500" />
          Advanced Actions
        </h3>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button 
            @click="rotateIP"
            :disabled="isProcessing"
            class="flex flex-col items-center justify-center p-4 rounded-xl border border-gray-200 hover:border-orange-300 hover:bg-orange-50 transition-all group"
          >
            <ArrowPathIcon class="w-8 h-8 text-gray-400 group-hover:text-orange-500 mb-2 transition-colors" :class="{ 'animate-spin': isRotating }" />
            <span class="text-sm font-medium text-gray-900">Rotate IP</span>
            <span class="text-xs text-gray-500 mt-1">Request new identity</span>
          </button>
          
          <!-- Placeholder for other actions like "Reset Keys" or "Clean Logs" -->
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import axios from 'axios';
import { 
  GlobeAltIcon, 
  WrenchScrewdriverIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon
} from '@heroicons/vue/24/outline';
import { ShieldCheckIcon, ServerStackIcon } from '@heroicons/vue/24/solid';

const customEndpoint = ref('');
const isProcessing = ref(false);
const isRotating = ref(false);
const statusData = ref({});
const restartRequired = ref(false);
let socket = null;

// Port config (loaded from API)
const socks5Port = ref(1080);
const panelPort = ref(8000);
const savedSocks5Port = ref(1080);
const savedPanelPort = ref(8000);

const portsChanged = computed(() => {
  return socks5Port.value !== savedSocks5Port.value || panelPort.value !== savedPanelPort.value;
});

const currentProtocol = computed(() => {
  return (statusData.value.warp_protocol || 'MASQUE').toUpperCase();
});

const canSwitchProtocol = computed(() => {
  const backend = statusData.value.backend || 'usque';
  const mode = statusData.value.warp_mode || 'proxy';
  return backend === 'official' && mode === 'tun';
});

const apiCall = async (method, url, data = null) => {
  try {
    const response = await axios[method](url, data);
    return response.data;
  } catch (err) {
    console.error(`API Error (${method} ${url}):`, err);
    return null;
  }
};

// Load port config
const loadPorts = async () => {
  const data = await apiCall('get', '/api/config/ports');
  if (data) {
    socks5Port.value = data.socks5_port;
    panelPort.value = data.panel_port;
    savedSocks5Port.value = data.socks5_port;
    savedPanelPort.value = data.panel_port;
  }
};

const savePorts = async () => {
  if (!portsChanged.value) return;
  isProcessing.value = true;
  
  const data = await apiCall('post', '/api/config/ports', {
    socks5_port: socks5Port.value,
    panel_port: panelPort.value,
  });
  
  if (data && data.success) {
    savedSocks5Port.value = data.socks5_port;
    savedPanelPort.value = data.panel_port;
    if (data.restart_required) {
      restartRequired.value = true;
    }
  }
  
  setTimeout(() => isProcessing.value = false, 1000);
};

const setEndpoint = async () => {
  isProcessing.value = true;
  await apiCall('post', '/api/config/endpoint', { endpoint: customEndpoint.value });
  setTimeout(() => isProcessing.value = false, 1000);
};

const toggleProtocol = async () => {
  isProcessing.value = true;
  const newProtocol = currentProtocol.value === 'MASQUE' ? 'wireguard' : 'masque';
  await apiCall('post', '/api/config/protocol', { protocol: newProtocol });
  setTimeout(() => isProcessing.value = false, 1000);
};

const rotateIP = async () => {
  isRotating.value = true;
  isProcessing.value = true;
  await apiCall('post', '/api/rotate');
  setTimeout(() => {
    isRotating.value = false;
    isProcessing.value = false;
  }, 1000);
};

// WebSocket for status sync
const connectWebSocket = () => {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.host}/ws/status`;
  socket = new WebSocket(wsUrl);
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === 'status') {
      statusData.value = message.data;
    }
  };
};

onMounted(() => {
  connectWebSocket();
  loadPorts();
});

onUnmounted(() => {
  if (socket) socket.close();
});
</script>
