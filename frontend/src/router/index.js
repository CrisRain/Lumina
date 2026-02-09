import { createRouter, createWebHistory } from 'vue-router';
import MainLayout from '../components/layout/MainLayout.vue';
import Dashboard from '../views/Dashboard.vue';
import KernelManager from '../views/KernelManager.vue';
import Logs from '../views/Logs.vue';
import Settings from '../views/Settings.vue';

const routes = [
    {
        path: '/',
        component: MainLayout,
        children: [
            {
                path: '',
                name: 'Dashboard',
                component: Dashboard
            },
            {
                path: 'kernel',
                name: 'KernelManager',
                component: KernelManager
            },
            {
                path: 'logs',
                name: 'Logs',
                component: Logs
            },
            {
                path: 'settings',
                name: 'Settings',
                component: Settings
            }
        ]
    }
];

const router = createRouter({
    history: createWebHistory(),
    routes
});

export default router;
