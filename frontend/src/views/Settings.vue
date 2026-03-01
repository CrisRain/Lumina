<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-2xl font-bold text-gray-900">Settings</h2>
      <p class="text-sm text-gray-500">Configure runtime ports and account security</p>
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

      <!-- Security Center -->
      <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 md:col-span-2">
        <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
          <ShieldCheckIcon class="w-5 h-5 text-emerald-500" />
          Security Center
        </h3>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="space-y-4">
            <div class="p-4 rounded-xl border border-emerald-100 bg-emerald-50/50">
              <p class="text-xs text-emerald-700 font-semibold uppercase tracking-wide">Sessions</p>
              <p class="mt-1 text-2xl font-bold text-emerald-900">{{ activeSessions }}</p>
              <p class="mt-1 text-xs text-emerald-700">Active panel sessions currently valid.</p>
            </div>

            <div class="flex flex-col sm:flex-row gap-3">
              <button
                @click="logoutOtherSessions"
                :disabled="isSecurityProcessing"
                class="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ isSecurityProcessing ? 'PROCESSING...' : 'LOG OUT OTHER SESSIONS' }}
              </button>
              <button
                @click="logoutCurrentSession"
                :disabled="isSecurityProcessing"
                class="px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-800 text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                LOG OUT THIS SESSION
              </button>
            </div>
          </div>

          <div class="space-y-3">
            <label class="block text-sm font-medium text-gray-700">Current Password</label>
            <input
              v-model="currentPassword"
              type="password"
              placeholder="Enter current password"
              class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 outline-none transition-all text-sm"
              :disabled="isSecurityProcessing"
            />

            <label class="block text-sm font-medium text-gray-700">New Password</label>
            <input
              v-model="newPassword"
              type="password"
              minlength="8"
              placeholder="At least 8 characters"
              class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 outline-none transition-all text-sm"
              :disabled="isSecurityProcessing"
            />

            <label class="block text-sm font-medium text-gray-700">Confirm New Password</label>
            <input
              v-model="confirmNewPassword"
              type="password"
              minlength="8"
              placeholder="Repeat new password"
              class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 outline-none transition-all text-sm"
              :disabled="isSecurityProcessing"
            />

            <p v-if="securityError" class="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {{ securityError }}
            </p>
            <p v-if="securitySuccess" class="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
              {{ securitySuccess }}
            </p>

            <div class="flex items-center justify-end pt-1">
              <button
                @click="changePassword"
                :disabled="isSecurityProcessing || !canChangePassword"
                class="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {{ isSecurityProcessing ? 'UPDATING...' : 'UPDATE PASSWORD' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import axios from 'axios';
import { ExclamationTriangleIcon, ShieldCheckIcon, ServerStackIcon } from '@heroicons/vue/24/outline';
import { useRouter } from 'vue-router';
import { useWarpActions } from '../composables/usePolling';

const { apiCall } = useWarpActions();
const router = useRouter();
const apiBase = import.meta.env.VITE_API_BASE_URL || '/api';

const isProcessing = ref(false);
const restartRequired = ref(false);
const isSecurityProcessing = ref(false);
const activeSessions = ref(1);
const currentPassword = ref('');
const newPassword = ref('');
const confirmNewPassword = ref('');
const securityError = ref('');
const securitySuccess = ref('');

// Port config (loaded from API)
const socks5Port = ref(1080);
const panelPort = ref(8000);
const savedSocks5Port = ref(1080);
const savedPanelPort = ref(8000);

const portsChanged = computed(() => {
  return socks5Port.value !== savedSocks5Port.value || panelPort.value !== savedPanelPort.value;
});

const canChangePassword = computed(() => {
  return (
    currentPassword.value.length > 0 &&
    newPassword.value.length >= 8 &&
    confirmNewPassword.value.length >= 8
  );
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

const loadSessions = async () => {
  try {
    const res = await axios.get(`${apiBase}/auth/sessions`);
    activeSessions.value = Number(res.data?.active_sessions ?? 1);
  } catch {
    activeSessions.value = 1;
  }
};

const resetSecurityMessages = () => {
  securityError.value = '';
  securitySuccess.value = '';
};

const changePassword = async () => {
  resetSecurityMessages();

  if (newPassword.value !== confirmNewPassword.value) {
    securityError.value = 'New passwords do not match.';
    return;
  }
  if (newPassword.value.length < 8) {
    securityError.value = 'New password must be at least 8 characters.';
    return;
  }

  isSecurityProcessing.value = true;
  try {
    const res = await axios.post(`${apiBase}/auth/password`, {
      current_password: currentPassword.value,
      new_password: newPassword.value
    });

    currentPassword.value = '';
    newPassword.value = '';
    confirmNewPassword.value = '';
    activeSessions.value = Number(res.data?.active_sessions ?? 1);

    const dropped = Number(res.data?.logged_out_others ?? 0);
    securitySuccess.value = dropped > 0
      ? `Password updated. Logged out ${dropped} other session(s).`
      : 'Password updated.';
  } catch (err) {
    securityError.value = err?.response?.data?.detail || 'Failed to update password.';
  } finally {
    isSecurityProcessing.value = false;
  }
};

const logoutOtherSessions = async () => {
  resetSecurityMessages();
  isSecurityProcessing.value = true;
  try {
    const res = await axios.post(`${apiBase}/auth/logout-all`, { keep_current: true });
    activeSessions.value = Number(res.data?.active_sessions ?? 1);
    const removed = Number(res.data?.removed_sessions ?? 0);
    securitySuccess.value = removed > 0
      ? `Logged out ${removed} other session(s).`
      : 'No other active sessions found.';
  } catch (err) {
    securityError.value = err?.response?.data?.detail || 'Failed to log out other sessions.';
  } finally {
    isSecurityProcessing.value = false;
  }
};

const logoutCurrentSession = async () => {
  resetSecurityMessages();
  if (!confirm('Log out current session now?')) return;

  isSecurityProcessing.value = true;
  try {
    await axios.post(`${apiBase}/auth/logout`);
  } catch {
    // If token is already invalid, proceed with local logout anyway.
  } finally {
    localStorage.removeItem('auth_token');
    isSecurityProcessing.value = false;
    router.push('/login');
  }
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
  loadSessions();
});
</script>
