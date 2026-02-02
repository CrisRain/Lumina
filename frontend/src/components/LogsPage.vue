<template>
  <div class="logs-page min-h-screen bg-gradient-to-br from-orange-50 via-white to-orange-50 text-gray-800 font-sans">
    <!-- Header -->
    <header class="px-6 py-5 backdrop-blur-md bg-white/80 border-b border-orange-200/50 shadow-sm">
      <div class="max-w-7xl mx-auto flex justify-between items-center">
        <div class="flex items-center gap-3">
          <router-link to="/" class="p-2 hover:bg-orange-100 rounded-lg transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </router-link>
          <div class="w-11 h-11 rounded-2xl bg-gradient-to-br from-orange-400 via-orange-500 to-orange-600 flex items-center justify-center shadow-lg shadow-orange-500/30">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <div>
            <h1 class="text-xl font-bold tracking-tight text-gray-900">Service Logs</h1>
            <p class="text-xs text-gray-500">Real-time system activity</p>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <!-- Log Level Filter -->
          <select 
            v-model="logLevelFilter"
            class="px-3 py-2 bg-white border border-orange-200 rounded-lg text-sm font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            <option value="all">All Levels</option>
            <option value="ERROR">Error</option>
            <option value="WARNING">Warning</option>
            <option value="INFO">Info</option>
            <option value="DEBUG">Debug</option>
          </select>
          
          <!-- Search -->
          <input 
            v-model="searchQuery"
            type="text"
            placeholder="Search logs..."
            class="px-4 py-2 bg-white border border-orange-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 w-64"
          />
          
          <!-- Actions -->
          <button 
            @click="clearLogs"
            class="px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 rounded-lg text-sm font-medium transition-all duration-200"
          >
            Clear Logs
          </button>
          <button 
            @click="downloadLogs"
            class="px-4 py-2 bg-orange-100 hover:bg-orange-200 text-orange-700 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download
          </button>
        </div>
      </div>
    </header>

    <!-- Tabs -->
    <div class="px-6 py-4 bg-white/50 border-b border-orange-200/30">
      <div class="max-w-7xl mx-auto flex gap-4">
        <button 
          @click="activeTab = 'system'"
          class="px-4 py-2 rounded-lg font-medium transition-colors"
          :class="activeTab === 'system' ? 'bg-orange-100 text-orange-700' : 'text-gray-600 hover:bg-white/60'"
        >
          System Logs
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <main class="p-6">
      <div class="max-w-7xl mx-auto">
        
        <!-- System Logs Tab -->
        <div v-show="activeTab === 'system'">
            <!-- Stats Cards -->
            <div class="grid grid-cols-4 gap-4 mb-6">
              <div class="bg-white/90 backdrop-blur-md border border-orange-200/60 rounded-xl p-4 shadow-lg">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-xs text-gray-500 mb-1">Total Logs</p>
                    <p class="text-2xl font-bold text-gray-900">{{ logs.length }}</p>
                  </div>
                  <div class="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                </div>
              </div>

              <div class="bg-white/90 backdrop-blur-md border border-red-200/60 rounded-xl p-4 shadow-lg">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-xs text-gray-500 mb-1">Errors</p>
                    <p class="text-2xl font-bold text-red-600">{{ errorCount }}</p>
                  </div>
                  <div class="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
              </div>

              <div class="bg-white/90 backdrop-blur-md border border-yellow-200/60 rounded-xl p-4 shadow-lg">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-xs text-gray-500 mb-1">Warnings</p>
                    <p class="text-2xl font-bold text-yellow-600">{{ warningCount }}</p>
                  </div>
                  <div class="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-yellow-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                </div>
              </div>

              <div class="bg-white/90 backdrop-blur-md border border-emerald-200/60 rounded-xl p-4 shadow-lg">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-xs text-gray-500 mb-1">Info</p>
                    <p class="text-2xl font-bold text-emerald-600">{{ infoCount }}</p>
                  </div>
                  <div class="w-12 h-12 bg-emerald-100 rounded-lg flex items-center justify-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                </div>
              </div>
            </div>

            <!-- Logs Container -->
            <div class="bg-white/90 backdrop-blur-md border border-orange-200/60 rounded-2xl shadow-xl overflow-hidden">
              <div 
                ref="logsContainer"
                class="bg-gray-900 p-6 font-mono text-sm min-h-[600px] max-h-[70vh] overflow-y-auto custom-scrollbar"
              >
                <div v-if="filteredLogs.length === 0" class="flex items-center justify-center h-64">
                  <div class="text-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 text-gray-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p class="text-gray-500">No logs available</p>
                  </div>
                </div>
                <div v-else class="space-y-1">
                  <div 
                    v-for="(log, index) in filteredLogs" 
                    :key="index"
                    class="flex gap-4 py-2 px-3 hover:bg-gray-800/70 rounded transition-colors duration-150 group"
                  >
                    <span class="text-gray-500 flex-shrink-0 w-20">{{ log.timestamp }}</span>
                    <span 
                      class="flex-shrink-0 font-semibold px-3 py-1 rounded text-xs uppercase tracking-wider w-24 text-center"
                      :class="getLogLevelClass(log.level)"
                    >
                      {{ log.level }}
                    </span>
                    <span class="text-gray-400 flex-shrink-0 w-48 truncate" :title="log.logger">{{ log.logger }}</span>
                    <span class="text-gray-300 break-all flex-1">{{ log.message }}</span>
                    <button 
                      @click="copyLog(log)"
                      class="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 text-orange-500 hover:text-orange-400"
                      title="Copy log"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
              
              <!-- Footer -->
              <div class="bg-white px-6 py-4 border-t border-gray-200 flex items-center justify-between">
                <div class="flex items-center gap-4 text-sm text-gray-600">
                  <span>Showing {{ filteredLogs.length }} of {{ logs.length }} logs</span>
                  <label class="flex items-center gap-2">
                    <input 
                      type="checkbox" 
                      v-model="autoScroll"
                      class="w-4 h-4 text-orange-600 border-gray-300 rounded focus:ring-orange-500"
                    />
                    <span>Auto-scroll</span>
                  </label>
                </div>
                <div class="text-xs text-gray-500">
                  Last updated: {{ lastUpdate }}
                </div>
              </div>
            </div>
        </div>


      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import axios from 'axios';



const activeTab = ref('system');
const logs = ref([]);
const searchQuery = ref('');
const logLevelFilter = ref('all');
const autoScroll = ref(true);
const logsContainer = ref(null);
const lastUpdate = ref('--:--:--');
let socket = null;

// Load cached logs from localStorage
const loadCachedLogs = () => {
  try {
    const cached = localStorage.getItem('warp_logs');
    if (cached) {
      logs.value = JSON.parse(cached);
    }
  } catch (err) {
    console.error('Failed to load cached logs:', err);
  }
};

// Save logs to localStorage
const saveLogs = () => {
  try {
    // Keep only last 1000 logs in cache
    const logsToSave = logs.value.slice(-1000);
    localStorage.setItem('warp_logs', JSON.stringify(logsToSave));
  } catch (err) {
    console.error('Failed to save logs:', err);
  }
};

// Computed properties
const filteredLogs = computed(() => {
  let filtered = logs.value;
  
  // Filter by level
  if (logLevelFilter.value !== 'all') {
    filtered = filtered.filter(log => log.level === logLevelFilter.value);
  }
  
  // Filter by search query
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase();
    filtered = filtered.filter(log => 
      log.message.toLowerCase().includes(query) ||
      log.logger.toLowerCase().includes(query)
    );
  }
  
  return filtered;
});

const errorCount = computed(() => logs.value.filter(l => l.level === 'ERROR').length);
const warningCount = computed(() => logs.value.filter(l => l.level === 'WARNING').length);
const infoCount = computed(() => logs.value.filter(l => l.level === 'INFO').length);

// Methods
const getLogLevelClass = (level) => {
  switch (level) {
    case 'ERROR':
      return 'bg-red-600 text-white';
    case 'WARNING':
      return 'bg-yellow-600 text-white';
    case 'INFO':
      return 'bg-blue-600 text-white';
    case 'DEBUG':
      return 'bg-gray-600 text-white';
    default:
      return 'bg-gray-500 text-white';
  }
};

const clearLogs = () => {
  if (confirm('Are you sure you want to clear all logs?')) {
    logs.value = [];
    localStorage.removeItem('warp_logs');
  }
};

const downloadLogs = () => {
  const content = logs.value.map(log => 
    `${log.timestamp} [${log.level}] ${log.logger} - ${log.message}`
  ).join('\n');
  
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `warp-logs-${new Date().toISOString().split('T')[0]}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

const copyLog = async (log) => {
  try {
    const text = `${log.timestamp} [${log.level}] ${log.logger} - ${log.message}`;
    await navigator.clipboard.writeText(text);
  } catch (err) {
    console.error('Failed to copy log:', err);
  }
};

const scrollToBottom = () => {
  if (autoScroll.value && logsContainer.value) {
    nextTick(() => {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight;
    });
  }
};

const connectWebSocket = () => {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${window.location.host}/ws/status`;
  
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log('WebSocket connected');
    fetchLogs();
  };

  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === 'log') {
      logs.value.push(message.data);
      // Keep only last 2000 logs in memory
      if (logs.value.length > 2000) {
        logs.value.shift();
      }
      lastUpdate.value = new Date().toLocaleTimeString();
      saveLogs();
      scrollToBottom();
    }
  };

  socket.onclose = () => {
    console.log('WebSocket disconnected. Reconnecting...');
    setTimeout(connectWebSocket, 3000);
  };

  socket.onerror = (err) => {
    console.error('WebSocket error:', err);
    socket.close();
  };
};

const fetchLogs = async () => {
  try {
    const response = await axios.get('/api/logs?limit=500');
    if (response.data && response.data.logs) {
      logs.value = response.data.logs;
      saveLogs();
      scrollToBottom();
    }
  } catch (err) {
    console.error('Failed to fetch logs:', err);
  }
};



onMounted(() => {
  loadCachedLogs();
  connectWebSocket();
  lastUpdate.value = new Date().toLocaleTimeString();
});

onUnmounted(() => {
  if (socket) {
    socket.close();
  }
});
</script>

<style scoped>
/* Custom Scrollbar */
.custom-scrollbar::-webkit-scrollbar {
  width: 10px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 5px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(249, 115, 22, 0.5);
  border-radius: 5px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(249, 115, 22, 0.7);
}
</style>
