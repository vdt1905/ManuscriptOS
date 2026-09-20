import { Search, LayoutDashboard, Component, Link as LinkIcon, Bell, Settings } from 'lucide-react';
import { Button } from './Button';
import { cn } from './Button';
import { NavLink } from 'react-router-dom';
import useAppStore from '../store/useAppStore';

export function Navbar() {
    const { isProcessing } = useAppStore();
    return (
        <header className="flex h-20 w-full shrink-0 items-center px-6 lg:px-10 justify-between">
            {/* Left Nav Links */}
            <nav className="flex items-center gap-8">
                {/* "/" only redirects; without `end` it matched every route and stayed highlighted */}
                <NavLink to="/dashboard" end className={({ isActive }) => cn("flex items-center gap-2 font-semibold text-base border-b-2 py-2", isActive ? "text-[var(--color-text-main)] border-[var(--color-primary-500)]" : "text-[var(--color-text-muted)] border-transparent hover:text-[var(--color-text-main)]", isProcessing && "opacity-50 pointer-events-none")}>
                    <LayoutDashboard className="w-5 h-5" /> Dashboard
                </NavLink>
                <NavLink to="/workflows" className={({ isActive }) => cn("flex items-center gap-2 font-semibold text-base border-b-2 py-2", isActive ? "text-[var(--color-text-main)] border-[var(--color-primary-500)]" : "text-[var(--color-text-muted)] border-transparent hover:text-[var(--color-text-main)]", isProcessing && "opacity-50 pointer-events-none")}>
                    <Component className="w-5 h-5" /> Workflows
                </NavLink>
                <NavLink to="/integrations" className={({ isActive }) => cn("flex items-center gap-2 font-semibold text-base border-b-2 py-2", isActive ? "text-[var(--color-text-main)] border-[var(--color-primary-500)]" : "text-[var(--color-text-muted)] border-transparent hover:text-[var(--color-text-main)]", isProcessing && "opacity-50 pointer-events-none")}>
                    <LinkIcon className="w-5 h-5" /> Integrations
                </NavLink>
            </nav>

            {/* Middle Search */}


            {/* Right Tools - Blank for now */}
            <div className="flex items-center gap-4">
            </div>
        </header>
    );
}
