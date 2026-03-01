<template>
  <div class="space-y-6">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Node Manager</h2>
        <p class="text-sm text-gray-500">Manage local and remote Lumina nodes from one panel</p>
      </div>
      <button
        @click="refreshNodes"
        :disabled="loading"
        class="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-700 text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <ArrowPathIcon class="w-4 h-4" :class="loading ? 'animate-spin' : ''" />
        {{ loading ? 'REFRESHING...' : 'REFRESH' }}
      </button>
    </div>

    <div class="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <h3 class="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
        <PlusCircleIcon class="w-5 h-5 text-indigo-500" />
        {{ isEditing ? 'Edit Remote Node' : 'Add Remote Node' }}
      </h3>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Node Name</label>
          <input
            v-model="form.name"
            type="text"
            placeholder="e.g. Tokyo VPS"
            class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all text-sm"
            :disabled="formLoading"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
          <input
            v-model="form.base_url"
            type="text"
            placeholder="https://node.example.com:8000"
            class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all text-sm font-mono"
            :disabled="formLoading"
          />
        </div>
      </div>

      <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Auth Token</label>
          <input
            v-model="form.token"
            type="text"
            :placeholder="isEditing ? 'Leave empty to keep existing token' : 'Optional bearer token'"
            class="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all text-sm font-mono"
            :disabled="formLoading || (isEditing && !replaceToken)"
          />
          <label v-if="isEditing" class="mt-2 inline-flex items-center gap-2 text-xs text-gray-600">
            <input type="checkbox" v-model="replaceToken" class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
            Replace saved token
          </label>
        </div>

        <div class="flex items-end">
          <label class="inline-flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" v-model="form.enabled" :disabled="formLoading" class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
            Node enabled
          </label>
        </div>
      </div>

      <div class="mt-5 flex items-center justify-end gap-3">
        <button
          v-if="isEditing"
          @click="resetForm"
          :disabled="formLoading"
          class="px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-800 text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          CANCEL
        </button>
        <button
          @click="saveNode"
          :disabled="formLoading"
          class="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ formLoading ? (isEditing ? 'UPDATING...' : 'ADDING...') : (isEditing ? 'UPDATE NODE' : 'ADD NODE') }}
        </button>
      </div>
    </div>

    <p v-if="error" class="text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
      {{ error }}
    </p>
    <p v-if="success" class="text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2">
      {{ success }}
    </p>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        v-for="node in sortedNodes"
        :key="node.id"
        class="bg-white rounded-2xl p-5 border shadow-sm"
        :class="node.is_local ? 'border-orange-200' : 'border-gray-100'"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <h3 class="text-base font-bold text-gray-900">{{ node.name }}</h3>
              <span
                class="text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide"
                :class="node.is_local ? 'bg-orange-100 text-orange-700' : 'bg-indigo-100 text-indigo-700'"
              >
                {{ node.is_local ? 'Local' : 'Remote' }}
              </span>
            </div>
            <p class="mt-1 text-xs text-gray-500 font-mono break-all">{{ node.base_url }}</p>
          </div>

          <span
            class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase"
            :class="connectionBadgeClass(node)"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-current"></span>
            {{ connectionLabel(node) }}
          </span>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3 text-xs">
          <div class="p-3 rounded-xl bg-gray-50 border border-gray-100">
            <p class="text-gray-500">Version</p>
            <p class="mt-1 font-semibold text-gray-900 font-mono">{{ node.version || 'Unknown' }}</p>
          </div>
          <div class="p-3 rounded-xl bg-gray-50 border border-gray-100">
            <p class="text-gray-500">Backend</p>
            <p class="mt-1 font-semibold text-gray-900">{{ node.status?.backend || 'Unknown' }}</p>
          </div>
          <div class="p-3 rounded-xl bg-gray-50 border border-gray-100">
            <p class="text-gray-500">IP</p>
            <p class="mt-1 font-semibold text-gray-900 font-mono">{{ node.status?.ip || '-' }}</p>
          </div>
          <div class="p-3 rounded-xl bg-gray-50 border border-gray-100">
            <p class="text-gray-500">Token</p>
            <p class="mt-1 font-semibold text-gray-900">{{ node.token_configured ? 'Configured' : 'None' }}</p>
          </div>
        </div>

        <p v-if="node.error" class="mt-3 text-xs text-red-700 bg-red-50 border border-red-100 rounded-lg px-2.5 py-2">
          {{ node.error }}
        </p>

        <div class="mt-4 flex flex-wrap gap-2">
          <button
            @click="connectNode(node.id)"
            :disabled="actionNodeId === node.id || (!node.is_local && !node.enabled)"
            class="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            CONNECT
          </button>
          <button
            @click="disconnectNode(node.id)"
            :disabled="actionNodeId === node.id || (!node.is_local && !node.enabled)"
            class="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-[11px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            DISCONNECT
          </button>
          <button
            @click="switchNodeBackend(node.id, 'usque')"
            :disabled="actionNodeId === node.id || (!node.is_local && !node.enabled)"
            class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            USE USQUE
          </button>
          <button
            @click="switchNodeBackend(node.id, 'official')"
            :disabled="actionNodeId === node.id || (!node.is_local && !node.enabled)"
            class="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-[11px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            USE OFFICIAL
          </button>

          <template v-if="!node.is_local">
            <button
              @click="editNode(node)"
              :disabled="actionNodeId === node.id"
              class="px-3 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-800 text-[11px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              EDIT
            </button>
            <button
              @click="removeNode(node)"
              :disabled="actionNodeId === node.id"
              class="px-3 py-1.5 rounded-lg bg-red-50 hover:bg-red-100 text-red-700 text-[11px] font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              DELETE
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import axios from 'axios';
import { ArrowPathIcon, PlusCircleIcon } from '@heroicons/vue/24/outline';

const apiBase = import.meta.env.VITE_API_BASE_URL || '/api';

const nodes = ref([]);
const loading = ref(false);
const formLoading = ref(false);
const actionNodeId = ref('');
const error = ref('');
const success = ref('');
const editingNodeId = ref('');
const replaceToken = ref(true);

const form = ref({
  name: '',
  base_url: '',
  token: '',
  enabled: true
});

const isEditing = computed(() => Boolean(editingNodeId.value));
const sortedNodes = computed(() => {
  return [...nodes.value].sort((a, b) => {
    if (a.is_local && !b.is_local) return -1;
    if (!a.is_local && b.is_local) return 1;
    return String(a.name || '').localeCompare(String(b.name || ''));
  });
});

const clearMessages = () => {
  error.value = '';
  success.value = '';
};

const refreshNodes = async () => {
  loading.value = true;
  try {
    const res = await axios.get(`${apiBase}/nodes/overview`);
    nodes.value = Array.isArray(res.data?.nodes) ? res.data.nodes : [];
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to load nodes.';
  } finally {
    loading.value = false;
  }
};

const resetForm = () => {
  editingNodeId.value = '';
  replaceToken.value = true;
  form.value = {
    name: '',
    base_url: '',
    token: '',
    enabled: true
  };
};

const saveNode = async () => {
  clearMessages();
  const name = form.value.name.trim();
  const baseUrl = form.value.base_url.trim();

  if (!name || !baseUrl) {
    error.value = 'Node name and base URL are required.';
    return;
  }

  formLoading.value = true;
  try {
    if (isEditing.value) {
      const payload = {
        name,
        base_url: baseUrl,
        enabled: Boolean(form.value.enabled)
      };
      if (replaceToken.value) {
        payload.token = form.value.token || '';
      }
      await axios.put(`${apiBase}/nodes/${editingNodeId.value}`, payload);
      success.value = 'Node updated.';
    } else {
      await axios.post(`${apiBase}/nodes`, {
        name,
        base_url: baseUrl,
        token: form.value.token || '',
        enabled: Boolean(form.value.enabled)
      });
      success.value = 'Node added.';
    }

    resetForm();
    await refreshNodes();
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to save node.';
  } finally {
    formLoading.value = false;
  }
};

const editNode = (node) => {
  clearMessages();
  editingNodeId.value = node.id;
  replaceToken.value = false;
  form.value = {
    name: node.name || '',
    base_url: node.base_url || '',
    token: '',
    enabled: Boolean(node.enabled)
  };
};

const removeNode = async (node) => {
  clearMessages();
  if (!confirm(`Delete node "${node.name}"?`)) return;

  actionNodeId.value = node.id;
  try {
    await axios.delete(`${apiBase}/nodes/${node.id}`);
    success.value = 'Node deleted.';
    if (editingNodeId.value === node.id) resetForm();
    await refreshNodes();
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to delete node.';
  } finally {
    actionNodeId.value = '';
  }
};

const runNodeAction = async (nodeId, endpoint, payload = null, successMessage = 'Action completed.') => {
  clearMessages();
  actionNodeId.value = nodeId;
  try {
    await axios.post(`${apiBase}/nodes/${nodeId}/${endpoint}`, payload);
    success.value = successMessage;
    await refreshNodes();
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Node action failed.';
  } finally {
    actionNodeId.value = '';
  }
};

const connectNode = async (nodeId) => {
  await runNodeAction(nodeId, 'connect', null, 'Connect command sent.');
};

const disconnectNode = async (nodeId) => {
  await runNodeAction(nodeId, 'disconnect', null, 'Disconnect command sent.');
};

const switchNodeBackend = async (nodeId, backend) => {
  await runNodeAction(nodeId, 'backend', { backend }, `Backend switched to ${backend}.`);
};

const connectionLabel = (node) => {
  if (!node.reachable) return 'Offline';
  const state = node.status?.status || 'unknown';
  if (state === 'connected') return 'Connected';
  if (state === 'disconnected') return 'Disconnected';
  return 'Unknown';
};

const connectionBadgeClass = (node) => {
  if (!node.reachable) return 'text-red-700 bg-red-100';
  const state = node.status?.status || 'unknown';
  if (state === 'connected') return 'text-emerald-700 bg-emerald-100';
  if (state === 'disconnected') return 'text-amber-700 bg-amber-100';
  return 'text-gray-700 bg-gray-100';
};

onMounted(() => {
  refreshNodes();
});
</script>
