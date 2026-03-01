<template>
  <div class="min-h-screen flex items-center justify-center py-10 px-4">
    <div class="w-full max-w-lg bg-white rounded-3xl border border-orange-100 shadow-xl shadow-orange-500/10 p-8">
      <h1 class="text-2xl font-bold text-gray-900">Initialize Lumina</h1>
      <p class="mt-2 text-sm text-gray-500">
        First-time setup: create an admin password and optional ports.
      </p>

      <form class="mt-6 space-y-4" @submit.prevent="submitSetup">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Admin Password</label>
          <input
            v-model="panelPassword"
            type="password"
            minlength="8"
            required
            placeholder="At least 8 characters"
            class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-100 outline-none text-sm"
          />
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">SOCKS5 Port</label>
            <input
              v-model.number="socks5Port"
              type="number"
              min="1"
              max="65535"
              class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-100 outline-none text-sm"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Panel Port</label>
            <input
              v-model.number="panelPort"
              type="number"
              min="1"
              max="65535"
              class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-100 outline-none text-sm"
            />
          </div>
        </div>

        <p v-if="error" class="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          {{ error }}
        </p>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-3 rounded-xl bg-orange-600 hover:bg-orange-700 text-white text-sm font-bold transition disabled:opacity-60"
        >
          {{ loading ? 'Initializing...' : 'Initialize' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';

const router = useRouter();
const panelPassword = ref('');
const socks5Port = ref(1080);
const panelPort = ref(8000);
const loading = ref(false);
const error = ref('');

const submitSetup = async () => {
  error.value = '';
  loading.value = true;
  const apiBase = import.meta.env.VITE_API_BASE_URL || '/api';

  const validPort = (v) => Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= 65535;
  if (!validPort(socks5Port.value) || !validPort(panelPort.value)) {
    error.value = 'Port must be between 1 and 65535.';
    loading.value = false;
    return;
  }

  try {
    const res = await axios.post(`${apiBase}/setup/initialize`, {
      panel_password: panelPassword.value,
      socks5_port: Number(socks5Port.value),
      panel_port: Number(panelPort.value),
    });

    if (res.data?.success) {
      router.push('/login');
    }
  } catch (err) {
    if (err?.response?.data?.detail) {
      error.value = err.response.data.detail;
    } else {
      error.value = 'Initialization failed';
    }
  } finally {
    loading.value = false;
  }
};
</script>
