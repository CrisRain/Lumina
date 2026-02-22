import { createRouter, createWebHistory } from 'vue-router';
import MainLayout from '../components/layout/MainLayout.vue';
import Dashboard from '../views/Dashboard.vue';
import KernelManager from '../views/KernelManager.vue';
import Logs from '../views/Logs.vue';
import Settings from '../views/Settings.vue';
import Login from '../views/Login.vue';
import axios from 'axios';

const routes = [
    {
        path: '/login',
        name: 'Login',
        component: Login,
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
            }
        ]
    }
];

const router = createRouter({
    history: createWebHistory(),
    routes
});

// Navigation Guard
router.beforeEach(async (to, from, next) => {
    if (to.meta.public) {
        next();
        return;
    }

    const apiBase = import.meta.env.VITE_API_BASE_URL || '/api';

    try {
        // Step 1: Check if a password is configured (public endpoint, no token needed)
        const statusRes = await axios.get(`${apiBase}/auth/status`);
        const requiresAuth = statusRes.data.requires_auth;

        if (!requiresAuth) {
            // No password configured — open access, let everyone through
            next();
            return;
        }

        // Step 2: Password is configured — we must have a valid token
        const token = localStorage.getItem('auth_token');
        if (!token) {
            next('/login');
            return;
        }

        // Step 3: Validate the token with the backend
        await axios.get(`${apiBase}/auth/check`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        next();
    } catch (error) {
        // Token invalid / expired, or network error
        localStorage.removeItem('auth_token');
        next('/login');
    }
});

export default router;
