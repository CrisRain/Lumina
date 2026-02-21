<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-2xl font-bold text-gray-900">Settings</h2>
      <p class="text-sm text-gray-500">Configure connection parameters and preferences</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      


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
import { ref, computed, onMounted } from 'vue';
import { 
  GlobeAltIcon, 
  WrenchScrewdriverIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon
} from '@heroicons/vue/24/outline';
import { ShieldCheckIcon, ServerStackIcon } from '@heroicons/vue/24/solid';
import { useStatus, useWarpActions } from '../composables/usePolling';

const { statusData } = useStatus();
const { rotateIP, isLoading: isRotating, apiCall } = useWarpActions();

const isProcessing = ref(false);
const restartRequired = ref(false);

// Port config (loaded from API)
const socks5Port = ref(1080);
const panelPort = ref(8000);
const savedSocks5Port = ref(1080);
const savedPanelPort = ref(8000);

const portsChanged = computed(() => {
  return socks5Port.value !== savedSocks5Port.value || panelPort.value !== savedPanelPort.value;
});

const loadPorts = async () => {
  const data = await apiCall('get', '/config/ports');
  if (!data) return;

  socks5Port.value = Number(data.socks5_port ?? 1080);
  panelPort.value = Number(data.panel_port ?? 8000);
  savedSocks5Port.value = socks5Port.value;
  savedPanelPort.value = panelPort.value;
  restartRequired.value = false;
};

const savePorts = async () => {
  if (!portsChanged.value) return;

  const socks5 = Number(socks5Port.value);
  const panel = Number(panelPort.value);
  const inRange = (p) => Number.isInteger(p) && p >= 1 && p <= 65535;
  if (!inRange(socks5) || !inRange(panel)) {
    alert('Invalid port number (must be 1-65535)');
    return;
  }

  isProcessing.value = true;
  const res = await apiCall('post', '/config/ports', { socks5_port: socks5, panel_port: panel });
  isProcessing.value = false;

  if (!res?.success) return;

  socks5Port.value = Number(res.socks5_port ?? socks5);
  panelPort.value = Number(res.panel_port ?? panel);
  savedSocks5Port.value = socks5Port.value;
  savedPanelPort.value = panelPort.value;
  restartRequired.value = Boolean(res.restart_required);
};

onMounted(() => {
  loadPorts();
});
</script>
