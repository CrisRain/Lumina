<template>
  <div class="space-y-6">
    <!-- Header Area -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Dashboard</h2>
        <p class="text-sm text-gray-500">Manage your secure connection</p>
      </div>
      
      <!-- Quick Controls removed -->
    </div>

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Left Column: Status & Connection -->
      <div class="lg:col-span-2 space-y-6">
        <!-- Big Connection Card -->
        <div class="bg-white rounded-3xl p-8 shadow-xl shadow-orange-500/5 border border-orange-100 relative overflow-hidden flex flex-col items-center justify-center text-center min-h-[400px]">
          <!-- Background Decoration -->
          <div class="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
            <div class="absolute -top-[50%] -left-[50%] w-[200%] h-[200%] bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-orange-50/50 via-transparent to-transparent opacity-50"></div>
          </div>

          <div class="relative z-10 flex flex-col items-center">
            <!-- Connection Button -->
            <button 
              @click="toggleConnection" 
              :disabled="isLoading"
              class="relative group transition-all duration-500 outline-none"
            >
              <div 
                class="w-48 h-48 rounded-full flex items-center justify-center transition-all duration-500 shadow-2xl"
                :class="[
                  isConnected ? 'bg-emerald-500 shadow-emerald-500/30' : 'bg-white shadow-gray-200',
                  isLoading ? 'cursor-wait' : 'hover:scale-105 active:scale-95 cursor-pointer'
                ]"
              >
                <!-- Rings -->
                <div class="absolute inset-0 rounded-full border-4 opacity-20" :class="isConnected ? 'border-emerald-200 scale-110' : 'border-gray-100 scale-110'"></div>
                <div class="absolute inset-0 rounded-full border-2 opacity-20" :class="isConnected ? 'border-emerald-200 scale-125' : 'border-gray-100 scale-125'"></div>
                
                <!-- Icon -->
                <div class="relative z-10">
                   <div v-if="isLoading" class="w-16 h-16 border-4 border-white/30 border-t-white rounded-full animate-spin"></div>
                   <PowerIcon v-else class="w-20 h-20 transition-colors duration-300" :class="isConnected ? 'text-white' : 'text-gray-300 group-hover:text-orange-500'" />
                </div>
              </div>
            </button>

            <!-- Status Text -->
            <div class="mt-8 space-y-2">
              <h3 class="text-3xl font-bold tracking-tight" :class="isConnected ? 'text-gray-900' : 'text-gray-400'">
                {{ isConnected ? 'Protected' : 'Disconnected' }}
              </h3>
              <p class="text-sm font-medium" :class="isConnected ? 'text-emerald-600' : 'text-gray-400'">
                {{ isConnected ? 'Your connection is secure.' : 'Traffic is not encrypted.' }}
              </p>
            </div>
            
            <!-- Protocol Badge -->
            <div class="mt-6">
               <span 
                class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider transition-colors"
                :class="isConnected ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-gray-100 text-gray-500'"
               >
                 <ShieldCheckIcon class="w-3.5 h-3.5" />
                 {{ protocol }}
               </span>
            </div>
          </div>
        </div>

        <!-- IP & Location Grid -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div class="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
            <p class="text-xs text-gray-500 font-medium mb-1">Public IP</p>
            <p class="font-mono font-semibold text-gray-900 truncate" :title="ipAddress">{{ ipAddress }}</p>
          </div>
          <div class="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
            <p class="text-xs text-gray-500 font-medium mb-1">Location</p>
            <p class="font-semibold text-gray-900 truncate" :title="city">{{ city }}</p>
          </div>
          <div class="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
            <p class="text-xs text-gray-500 font-medium mb-1">Country</p>
            <p class="font-semibold text-gray-900 truncate" :title="country">{{ country }}</p>
          </div>
          <div class="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
            <p class="text-xs text-gray-500 font-medium mb-1">ISP</p>
            <p class="font-semibold text-gray-900 truncate" :title="isp">{{ isp }}</p>
          </div>
        </div>
      </div>

      <!-- Right Column: Proxy & Details -->
      <div class="flex flex-col h-full gap-6">
        <!-- Proxy Cards -->
        <div class="bg-white rounded-2xl shadow-lg shadow-orange-500/5 border border-orange-100 p-6">
          <h3 class="text-sm font-bold text-gray-900 uppercase tracking-wider mb-4 flex items-center gap-2">
            <ArrowsRightLeftIcon class="w-4 h-4 text-orange-500" />
            Proxy Settings
          </h3>
          
          <div class="space-y-4">
            <!-- SOCKS5 -->
            <div class="p-4 bg-gray-50 rounded-xl border border-gray-200 group hover:border-orange-300 transition-colors">
              <div class="flex justify-between items-start mb-2">
                <span class="text-xs font-semibold text-gray-500 uppercase">SOCKS5</span>
                <button @click="copyToClipboard(proxyAddress)" class="text-gray-400 hover:text-orange-600 transition-colors">
                  <DocumentDuplicateIcon class="w-4 h-4" />
                </button>
              </div>
              <p class="font-mono text-sm text-gray-900 break-all">{{ proxyAddress }}</p>
            </div>

            <!-- HTTP -->
            <div class="p-4 bg-gray-50 rounded-xl border border-gray-200 group hover:border-blue-300 transition-colors">
              <div class="flex justify-between items-start mb-2">
                <span class="text-xs font-semibold text-gray-500 uppercase">HTTP</span>
                <button @click="copyToClipboard(httpProxyAddress)" class="text-gray-400 hover:text-blue-600 transition-colors">
                  <DocumentDuplicateIcon class="w-4 h-4" />
                </button>
              </div>
              <p class="font-mono text-sm text-gray-900 break-all">{{ httpProxyAddress }}</p>
            </div>
          </div>
        </div>

        <!-- Recent Logs Preview -->
        <div class="bg-white rounded-2xl shadow-lg shadow-orange-500/5 border border-orange-100 p-6 flex flex-col flex-1 min-h-[200px]">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
              <CommandLineIcon class="w-4 h-4 text-gray-500" />
              Activity
            </h3>
            <router-link to="/logs" class="text-xs font-medium text-orange-600 hover:text-orange-700 flex items-center gap-1">
              View All <ArrowRightIcon class="w-3 h-3" />
            </router-link>
          </div>
          
          <div class="flex-1 bg-gray-900 rounded-xl p-4 overflow-hidden relative group">
             <div class="absolute inset-0 overflow-y-auto custom-scrollbar p-4 space-y-2">
               <div v-if="logs.length === 0" class="text-gray-600 text-xs text-center mt-10">No activity recorded</div>
               <div v-for="(log, i) in logs.slice(-10).reverse()" :key="i" class="text-[10px] font-mono border-l-2 pl-2" :class="getLogColor(log.level)">
                 <span class="opacity-50">{{ log.timestamp.split(' ')[1] }}</span> 
                 <span class="ml-1 text-gray-300">{{ log.message }}</span>
               </div>
             </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue';
import axios from 'axios';
import { 
  PowerIcon, 
  ShieldCheckIcon, 
  ArrowsRightLeftIcon, 
  DocumentDuplicateIcon, 
  CommandLineIcon,
  ArrowRightIcon,
  ChevronDownIcon,
  CheckIcon
} from '@heroicons/vue/24/outline';

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

// Computed
const isConnected = computed(() => statusData.value.status === 'connected');
const ipAddress = computed(() => statusData.value.ip || statusData.value.details?.ip || 'Unknown');
const city = computed(() => statusData.value.city || statusData.value.details?.city || 'Unknown');
const country = computed(() => statusData.value.country || statusData.value.location || 'Unknown');
const isp = computed(() => statusData.value.isp || statusData.value.details?.isp || 'Cloudflare WARP');
const protocol = computed(() => statusData.value.warp_protocol || statusData.value.protocol || 'MASQUE');
const proxyAddress = computed(() => statusData.value.proxy_address || 'socks5://127.0.0.1:1080');
const httpProxyAddress = computed(() => statusData.value.http_proxy_address || 'http://127.0.0.1:8080');
const warpMode = computed(() => statusData.value.warp_mode || 'proxy');
const backend = computed(() => statusData.value.backend || 'usque');

// API Helpers
const apiCall = async (method, url, data = null) => {
  try {
    const response = await axios[method](url, data);
    return response.data;
  } catch (err) {
    console.error(`API Error (${method} ${url}):`, err);
    return null;
  }
};

// Actions
const toggleConnection = async () => {
  isLoading.value = true;
  if (isConnected.value) {
    await apiCall('post', '/api/disconnect');
  } else {
    await apiCall('post', '/api/connect');
  }
  // Loading state will be cleared by next status update or timeout
  setTimeout(() => isLoading.value = false, 2000);
};

const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    // Could add toast notification here
  } catch (err) {
    console.error('Failed to copy:', err);
  }
};

const getLogColor = (level) => {
  switch (level) {
    case 'ERROR': return 'border-red-500';
    case 'WARNING': return 'border-yellow-500';
    case 'INFO': return 'border-blue-500';
    default: return 'border-gray-500';
  }
};

// WebSocket
const connectWebSocket = () => {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.host}/ws/status`;
  
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    // console.log('WebSocket connected');
    // Fetch initial logs
    apiCall('get', '/api/logs?limit=20').then(data => {
        if(data && data.logs) logs.value = data.logs;
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
    }
  };

  socket.onclose = () => {
    setTimeout(connectWebSocket, 3000);
  };
};

onMounted(() => {
  connectWebSocket();
});

onUnmounted(() => {
  if (socket) socket.close();
});
</script>
