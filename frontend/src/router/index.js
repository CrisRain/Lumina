import { createRouter, createWebHistory } from 'vue-router';
import HomePage from '../components/HomePage.vue';
import LogsPage from '../components/LogsPage.vue';

const routes = [
    {
        path: '/',
        name: 'Home',
        component: HomePage
    },
    {
        path: '/logs',
        name: 'Logs',
        component: LogsPage
    }
];

const router = createRouter({
    history: createWebHistory(),
    routes
});

export default router;
