import React from 'react';
import { Toaster, toast } from 'react-hot-toast';

export const ToastProvider = ({ children }) => {
    return (
        <>
            {children}
            <Toaster
                position="top-center"
                toastOptions={{
                    duration: 3000,
                    style: {
                        background: 'var(--color-surface-100)',
                        color: 'var(--color-text-main)',
                        border: '1px solid var(--color-surface-200)',
                        borderRadius: 'var(--radius-md)',
                        boxShadow: 'var(--shadow-floating)',
                    },
                    success: {
                        iconTheme: {
                            primary: 'var(--color-primary-500)',
                            secondary: '#fff',
                        },
                    },
                    error: {
                        iconTheme: {
                            primary: '#ef4444',
                            secondary: '#fff',
                        },
                    },
                }}
            />
        </>
    );
};

// One shared object: hooks that list `toast` as an effect dependency would
// otherwise re-run on every render (a fresh object each call fired the
// "could not load documents" toast on every keystroke).
const toastApi = {
        toast: ({ title, description, variant = 'info' }) => {
            const message = description ? `${title}: ${description}` : title;

            if (variant === 'success') {
                toast.success(message);
            } else if (variant === 'error' || variant === 'destructive') {
                toast.error(message);
            } else {
                toast(message);
            }
        },
        confirm: ({ title, description, confirmText = 'Confirm', variant = 'destructive', onConfirm }) => {
            toast((t) => (
                <div className="flex flex-col gap-3 min-w-[280px]">
                    <div>
                        <h4 className="font-bold text-[var(--color-text-main)] text-sm">{title}</h4>
                        {description && <p className="text-xs text-[var(--color-text-muted)] mt-1">{description}</p>}
                    </div>
                    <div className="flex justify-end gap-2 mt-2">
                        <button
                            onClick={() => toast.dismiss(t.id)}
                            className="px-3 py-1.5 text-xs font-semibold text-[var(--color-text-muted)] hover:bg-[var(--color-surface-200)] rounded transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={() => {
                                toast.dismiss(t.id);
                                onConfirm();
                            }}
                            className={`px-3 py-1.5 text-xs font-bold text-white rounded shadow-sm transition-colors ${variant === 'destructive' ? 'bg-red-500 hover:bg-red-600' : 'bg-[var(--color-primary-600)] hover:bg-[var(--color-primary-700)]'}`}
                        >
                            {confirmText}
                        </button>
                    </div>
                </div>
            ), {
                duration: Infinity,
                position: "top-center",
                style: {
                    border: variant === 'destructive' ? '1px solid #fca5a5' : '1px solid var(--color-primary-300)',
                    padding: '16px'
                }
            });
        },
};

// Custom hook to maintain compatibility with existing codebase
export const useToast = () => toastApi;
