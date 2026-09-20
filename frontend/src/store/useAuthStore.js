import { create } from 'zustand';
import { authService } from '../services';

// Auth session state (client state — stays in Zustand). All network I/O goes
// through authService; errors arrive pre-normalized as { message, status }.
// A stored token means a session check is about to run. Starting in 'loading'
// keeps ProtectedRoute from redirecting to "/" on the very first render (it
// renders before App's effect calls checkAuth), which sent every refresh and
// deep link to the dashboard.
const hasStoredToken = () => {
    try { return Boolean(localStorage.getItem('token')); } catch { return false; }
};

const useAuthStore = create((set) => ({
    user: null,
    isAuthenticated: false,
    status: hasStoredToken() ? 'loading' : 'idle', // 'idle' | 'loading' | 'error' | 'success'
    errorMessage: null,

    // Initialize state from a stored token.
    checkAuth: async () => {
        const token = localStorage.getItem('token');
        if (!token) {
            set({ isAuthenticated: false, user: null, status: 'idle' });
            return;
        }
        set({ status: 'loading', errorMessage: null });
        try {
            const user = await authService.getProfile();
            set({ user, isAuthenticated: true, status: 'success' });
        } catch (error) {
            localStorage.removeItem('token');
            set({ user: null, isAuthenticated: false, status: 'error', errorMessage: error.message });
        }
    },

    login: async (email, password) => {
        set({ status: 'loading', errorMessage: null });
        try {
            const data = await authService.login(email, password);
            localStorage.setItem('token', data.token);
            set({ user: data.user || data, isAuthenticated: true, status: 'success' });
            return true;
        } catch (error) {
            set({ status: 'error', errorMessage: error.message });
            return false;
        }
    },

    signup: async (username, email, password) => {
        set({ status: 'loading', errorMessage: null });
        try {
            const data = await authService.signup(username, email, password);
            localStorage.setItem('token', data.token);
            set({ user: data.user || data, isAuthenticated: true, status: 'success' });
            return true;
        } catch (error) {
            set({ status: 'error', errorMessage: error.message });
            return false;
        }
    },

    logout: () => {
        localStorage.removeItem('token');
        set({ user: null, isAuthenticated: false, status: 'idle' });
    },

    updateProfilePic: async (file) => {
        if (!localStorage.getItem('token')) return false;
        set({ status: 'loading', errorMessage: null });
        try {
            const user = await authService.updateProfilePic(file);
            set({ user, status: 'success' });
            return true;
        } catch (error) {
            set({ status: 'error', errorMessage: error.message });
            return false;
        }
    },

    clearError: () => set({ errorMessage: null, status: 'idle' })
}));

export default useAuthStore;
