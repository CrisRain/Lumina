<template>
  <div class="space-y-6">
    <!-- Header Area -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Dashboard</h2>
        <p class="text-sm text-gray-500">Manage your secure connection</p>
      </div>
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
              @click="onToggle" 
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
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
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
          
          <div ref="activityContainer" class="bg-gray-900 rounded-xl overflow-y-auto custom-scrollbar h-60">
            <div class="p-4 space-y-1.5">
              <div v-if="logs.length === 0" class="text-gray-600 text-xs text-center py-10">No activity recorded</div>
              <div v-for="(log, i) in recentLogs" :key="i" class="text-[11px] font-mono leading-relaxed border-l-2 pl-2 py-0.5" :class="getLogColor(log.level)">
                <span class="text-gray-400 select-none font-medium">{{ formatTime(log.timestamp) }}</span>
                <span class="ml-2 text-gray-300 break-all whitespace-pre-wrap">{{ log.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { 
  PowerIcon, 
  ShieldCheckIcon, 
  ArrowsRightLeftIcon, 
  DocumentDuplicateIcon, 
  CommandLineIcon,
  ArrowRightIcon,
} from '@heroicons/vue/24/outline';
import { useStatus, useLogs, useWarpActions } from '../composables/usePolling';

const { isConnected, ipAddress, city, country, isp, protocol, proxyAddress } = useStatus();
const { logs } = useLogs();
const { isLoading, toggleConnection } = useWarpActions();

const activityContainer = ref(null);

const onToggle = () => toggleConnection(isConnected.value);

// Show last 15 logs, newest at bottom (natural reading order)
const recentLogs = computed(() => logs.value.slice(-15));

// Extract time portion from timestamp like "12:13:15" or "2026-02-11 12:13:15"
const formatTime = (ts) => {
  if (!ts) return '';
  const parts = ts.split(' ');
  const timePart = parts.length > 1 ? parts[parts.length - 1] : ts;
  return timePart.split('.')[0];
};

const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
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
</script>
