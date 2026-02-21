<template>
  <!-- Constrain height to viewport minus layout padding (Mobile: ~6rem, Desktop: ~4rem) -->
  <div class="flex flex-col space-y-4 h-[calc(100vh-6rem)] md:h-[calc(100vh-4rem)]">
    <!-- Header Controls -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 flex-shrink-0">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Service Logs</h2>
        <p class="text-sm text-gray-500">Real-time system activity and debugging</p>
      </div>

      <div class="flex items-center gap-3">
        <!-- Log Level Filter -->
        <select 
          v-model="logLevelFilter"
          class="px-3 py-2 bg-white border border-gray-200 rounded-xl text-sm font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-orange-500 shadow-sm"
        >
          <option value="all">All Levels</option>
          <option value="ERROR">Error</option>
          <option value="WARNING">Warning</option>
          <option value="INFO">Info</option>
          <option value="DEBUG">Debug</option>
        </select>
        
        <!-- Search -->
        <div class="relative">
           <input 
            v-model="searchQuery"
            type="text"
            placeholder="Search logs..."
            class="pl-9 pr-4 py-2 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 w-64 shadow-sm"
          />
          <MagnifyingGlassIcon class="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
        </div>
        
        <!-- Actions -->
        <button 
          @click="clearLogs"
          class="p-2 bg-white hover:bg-red-50 text-gray-600 hover:text-red-600 border border-gray-200 rounded-xl transition-all shadow-sm"
          title="Clear Logs"
        >
          <TrashIcon class="w-5 h-5" />
        </button>
        <button 
          @click="downloadLogs"
          class="flex items-center gap-2 px-4 py-2 bg-white hover:bg-orange-50 text-gray-700 hover:text-orange-700 border border-gray-200 rounded-xl font-medium transition-all shadow-sm"
        >
          <ArrowDownTrayIcon class="w-4 h-4" />
          <span>Download</span>
        </button>
      </div>
    </div>

    <!-- Stats Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 flex-shrink-0">
      <div class="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
        <div>
          <p class="text-xs text-gray-500 font-medium">Total</p>
          <p class="text-xl font-bold text-gray-900">{{ logs.length }}</p>
        </div>
        <div class="p-2 bg-gray-100 rounded-lg"><ListBulletIcon class="w-5 h-5 text-gray-500" /></div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
        <div>
          <p class="text-xs text-gray-500 font-medium">Errors</p>
          <p class="text-xl font-bold text-red-600">{{ errorCount }}</p>
        </div>
        <div class="p-2 bg-red-50 rounded-lg"><ExclamationCircleIcon class="w-5 h-5 text-red-500" /></div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
        <div>
          <p class="text-xs text-gray-500 font-medium">Warnings</p>
          <p class="text-xl font-bold text-yellow-600">{{ warningCount }}</p>
        </div>
        <div class="p-2 bg-yellow-50 rounded-lg"><ExclamationTriangleIcon class="w-5 h-5 text-yellow-500" /></div>
      </div>
      <div class="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex items-center justify-between">
        <div>
          <p class="text-xs text-gray-500 font-medium">Info</p>
          <p class="text-xl font-bold text-blue-600">{{ infoCount }}</p>
        </div>
        <div class="p-2 bg-blue-50 rounded-lg"><InformationCircleIcon class="w-5 h-5 text-blue-500" /></div>
      </div>
    </div>

    <!-- Logs Console -->
    <!-- min-h-0 is crucial for nested flex scrolling -->
    <div class="flex-1 bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden flex flex-col min-h-0">
      <div 
        ref="logsContainer"
        class="flex-1 bg-[#1e1e1e] p-4 font-mono text-xs overflow-y-auto custom-scrollbar"
      >
        <div v-if="filteredLogs.length === 0" class="flex items-center justify-center h-full text-gray-500">
          No logs matching criteria
        </div>
        <div v-else class="space-y-0.5">
          <div 
            v-for="(log, index) in filteredLogs" 
            :key="index"
            class="flex flex-col md:flex-row md:gap-3 py-2 px-2 hover:bg-[#2a2a2a] rounded transition-colors group items-start border-b border-[#2a2a2a] md:border-none"
          >
            <div class="flex items-center gap-2 md:contents w-full">
              <span class="text-gray-500 text-[10px] md:text-xs flex-shrink-0 md:w-32 select-none">{{ log.timestamp }}</span>
              <span 
                class="flex-shrink-0 font-bold text-[10px] md:text-xs md:w-16"
                :class="getLogLevelColor(log.level)"
              >
                {{ log.level }}
              </span>
              <span class="text-gray-400 text-[10px] md:text-xs flex-shrink-0 md:w-32 truncate select-none md:hidden">[{{ log.logger }}]</span>
            </div>
            <span class="text-gray-400 text-xs flex-shrink-0 w-32 truncate select-none hidden md:block" :title="log.logger">[{{ log.logger }}]</span>
            <span class="text-gray-300 break-all flex-1 whitespace-pre-wrap mt-1 md:mt-0">{{ log.message }}</span>
          </div>
        </div>
      </div>
      
      <!-- Console Footer -->
      <div class="bg-gray-50 px-4 py-2 border-t border-gray-200 flex items-center justify-between text-xs text-gray-500">
        <div class="flex items-center gap-4">
           <label class="flex items-center gap-2 cursor-pointer hover:text-gray-700">
            <input 
              type="checkbox" 
              v-model="autoScroll"
              class="rounded border-gray-300 text-orange-600 focus:ring-orange-500"
            />
            <span>Auto-scroll</span>
          </label>
        </div>
        <div>Last updated: {{ lastUpdate }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue';
import { 
  MagnifyingGlassIcon, 
  TrashIcon, 
  ArrowDownTrayIcon,
  ListBulletIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon
} from '@heroicons/vue/24/outline';
import { useLogs } from '../composables/usePolling';

const { logs } = useLogs();

const searchQuery = ref('');
const logLevelFilter = ref('all');
const autoScroll = ref(true);
const logsContainer = ref(null);
const lastUpdate = ref(new Date().toLocaleTimeString());

const filteredLogs = computed(() => {
  let filtered = logs.value;
  if (logLevelFilter.value !== 'all') {
    filtered = filtered.filter(log => log.level === logLevelFilter.value);
  }
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

const getLogLevelColor = (level) => {
  switch (level) {
    case 'ERROR': return 'text-red-500';
    case 'WARNING': return 'text-yellow-500';
    case 'INFO': return 'text-blue-400';
    case 'DEBUG': return 'text-gray-400';
    default: return 'text-gray-500';
  }
};

const scrollToBottom = () => {
  if (autoScroll.value && logsContainer.value) {
    nextTick(() => {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight;
    });
  }
};

watch(logs, () => {
    lastUpdate.value = new Date().toLocaleTimeString();
    scrollToBottom();
}, { deep: true });

const clearLogs = () => logs.value = [];

const downloadLogs = () => {
  const content = logs.value.map(log => `${log.timestamp} [${log.level}] ${log.logger} - ${log.message}`).join('\n');
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `lumina-logs-${new Date().toISOString().split('T')[0]}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

</script>
