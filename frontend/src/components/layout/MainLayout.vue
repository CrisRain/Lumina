<template>
  <div class="flex h-screen w-full bg-[#FAFAFA] text-gray-800 font-sans overflow-hidden">
    <!-- Mobile Header -->
    <div class="md:hidden fixed top-0 left-0 right-0 h-16 bg-white/80 backdrop-blur-md border-b border-gray-100 z-30 flex items-center px-4 justify-between">
      <div class="flex items-center gap-3">
        <button 
          @click="isSidebarOpen = true"
          class="p-2 -ml-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <Bars3Icon class="w-6 h-6" />
        </button>
        <span class="font-bold text-gray-900 tracking-tight">Lu<span class="text-orange-600">mina</span></span>
      </div>
    </div>

    <!-- Mobile Overlay -->
    <div 
      v-if="isSidebarOpen" 
      @click="isSidebarOpen = false" 
      class="fixed inset-0 bg-black/20 z-40 md:hidden backdrop-blur-sm transition-opacity"
    ></div>

    <!-- Sidebar -->
    <Sidebar 
      :isOpen="isSidebarOpen" 
      @close="isSidebarOpen = false"
    />

    <!-- Main Content Area -->
    <div class="flex-1 flex flex-col h-screen overflow-hidden relative pt-16 md:pt-0">
      <!-- Ambient Background -->
      <div class="absolute inset-0 pointer-events-none z-0">
        <div class="absolute top-[-20%] right-[-10%] w-[800px] h-[800px] bg-gradient-to-br from-orange-100/40 via-orange-50/20 to-transparent rounded-full blur-3xl opacity-60 animate-float"></div>
        <div class="absolute bottom-[-10%] left-[-10%] w-[600px] h-[600px] bg-gradient-to-tr from-indigo-50/40 via-white to-transparent rounded-full blur-3xl opacity-60 animate-float-delayed"></div>
      </div>

      <!-- Content Scrollable Area -->
      <main class="flex-1 overflow-y-auto overflow-x-hidden relative z-10 custom-scrollbar">
        <div class="max-w-7xl mx-auto p-4 md:p-8">
           <router-view v-slot="{ Component }">
            <transition 
              name="fade-slide" 
              mode="out-in"
              appear
            >
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { Bars3Icon } from '@heroicons/vue/24/outline';
import Sidebar from './Sidebar.vue';

const isSidebarOpen = ref(false);
const route = useRoute();

// Close sidebar on route change (mobile)
watch(() => route.path, () => {
  isSidebarOpen.value = false;
});
</script>

<style>
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* Custom Scrollbar for the main area */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(200, 200, 200, 0.3);
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(200, 200, 200, 0.5);
}
</style>
