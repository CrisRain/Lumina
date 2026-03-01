import { createRouter, createWebHistory } from 'vue-router';
import MainLayout from '../components/layout/MainLayout.vue';
import Dashboard from '../views/Dashboard.vue';
import KernelManager from '../views/KernelManager.vue';
import Logs from '../views/Logs.vue';
import Settings from '../views/Settings.vue';
import NodeManager from '../views/NodeManager.vue';
import Login from '../views/Login.vue';
import Setup from '../views/Setup.vue';
import axios from 'axios';

const routes = [
    {
        path: '/login',
        name: 'Login',
        component: Login,
        meta: { public: true }
    },
    {
        path: '/setup',
        name: 'Setup',
        component: Setup,
        meta: { public: true }
    },
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
            },
            {
                path: 'nodes',
                name: 'NodeManager',
                component: NodeManager
            }
        ]
    }
];

const router = createRouter({
    history: createWebHistory(),
    routes
});

router.beforeEach(async (to, from, next) => {
    const apiBase = import.meta.env.VITE_API_BASE_URL || '/api';

    try {
        const setupRes = await axios.get(`${apiBase}/setup/status`);
        const initialized = Boolean(setupRes.data?.initialized);

        if (!initialized) {
            if (to.name === 'Setup') {
                next();
                return;
            }
            next('/setup');
            return;
        }

        if (to.name === 'Setup') {
            next('/login');
            return;
        }

        if (to.meta.public) {
            if (to.name === 'Login') {
                const authStatusRes = await axios.get(`${apiBase}/auth/status`);
                if (!authStatusRes.data?.requires_auth) {
                    next('/');
                    return;
                }
            }
            next();
            return;
        }

        const statusRes = await axios.get(`${apiBase}/auth/status`);
        const requiresAuth = Boolean(statusRes.data?.requires_auth);

        if (!requiresAuth) {
            next();
            return;
        }

        const token = localStorage.getItem('auth_token');
        if (!token) {
            next('/login');
            return;
        }

        await axios.get(`${apiBase}/auth/check`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        next();
    } catch (error) {
        localStorage.removeItem('auth_token');
        if (to.name === 'Setup') {
            next();
            return;
        }
        next('/login');
    }
});

export default router;
