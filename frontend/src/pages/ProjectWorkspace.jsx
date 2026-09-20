// ProjectWorkspace — the file editor workspace (Track A5 decomposition).
// This component owns ALL state + handlers (orchestrator). Presentational pieces
// live under ./project-workspace/: FileTree (left), LatexEditorPane, EmptyState.
// The MD + Quill editor branches stay inline (small, tightly coupled to state).
import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { Loader2, Save, Play, Microscope } from 'lucide-react';
import { Button } from '../components/Button';
import { useToast } from '../components/Toasts';
import useProjectStore from '../store/useProjectStore';
import { useRenameProject, useDeleteProject } from '../hooks/queries/useProjectQueries';
import useAppStore from '../store/useAppStore';
import ReactQuill from 'react-quill-new';
import 'react-quill-new/dist/quill.snow.css';
import MDEditor from '@uiw/react-md-editor';
import { ENDPOINTS, authHeaders } from '../config/api';
import { FileTree } from './project-workspace/FileTree';
import { LatexEditorPane } from './project-workspace/LatexEditorPane';
import { EmptyState } from './project-workspace/EmptyState';

const API_URL = ENDPOINTS.projects;

function ProjectWorkspaceInner() {
    const latexPreviewRef = useRef(null);
    const { id } = useParams();
    const navigate = useNavigate();
    const location = useLocation();
    const [project, setProject] = useState(null);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [activeFileId, setActiveFileId] = useState(
        // Pre-activate a file passed via navigation state (e.g. after reconstruct)
        location.state?.activeFileId || null
    );
    const [localContent, setLocalContent] = useState('');

    // UI states for renaming
    const [isEditingProject, setIsEditingProject] = useState(false);
    const [editingProjectTitle, setEditingProjectTitle] = useState('');
    const [editingFileId, setEditingFileId] = useState(null);
    const [editingFileName, setEditingFileName] = useState('');

    const recordVisit = useProjectStore((s) => s.recordVisit);
    const renameProject = useRenameProject();
    const deleteProject = useDeleteProject();
    const { toast, confirm } = useToast();
    const { setDeepScanProjectId, setDeepScanSourceFileName, setChatContext } = useAppStore();

    // Dockyyy (the chat bot) silently reads the document that is open here.
    useEffect(() => {
        setChatContext(localContent);
        return () => setChatContext('');
    }, [localContent, setChatContext]);
    const fileInputRef = useRef(null);
    const saveTimeoutRef = useRef(null);

    // LaTeX editor state
    const latexEditorRef = useRef(null);
    const [latexCompiling, setLatexCompiling] = useState(false);
    const [latexCompiled, setLatexCompiled] = useState(false);
    const [dirty, setDirty] = useState(false);   // edits the server hasn't got yet
    const pendingRef = useRef(null);              // { id, fileId, content } waiting for the autosave timer
    const [latexOutline, setLatexOutline] = useState([]);

    const fetchProject = async ({ selectFirst = false } = {}) => {
        try {
            const token = localStorage.getItem('token');
            const res = await axios.get(`${API_URL}/${id}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setProject(res.data);
            recordVisit(res.data);
            if (res.data.files?.length > 0 && selectFirst) {
                setActiveFileId(res.data.files[0]._id);
            }
        } catch (error) {
            toast({ title: 'Error', description: 'Failed to load workspace', variant: 'error' });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        // A file passed via navigation state is already selected; otherwise
        // open the project's first file.
        fetchProject({ selectFirst: !location.state?.activeFileId });

        return () => {
            clearTimeout(saveTimeoutRef.current);
            // Flush an autosave that was still counting down, so the last
            // couple of seconds of typing survive navigating away.
            const pending = pendingRef.current;
            if (pending) {
                pendingRef.current = null;
                axios.put(`${API_URL}/${pending.id}/files/${pending.fileId}`, { content: pending.content }, {
                    headers: authHeaders(),
                }).catch(() => { /* nothing sensible to show after leaving the page */ });
            }
        };
    }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

    const activeFile = project?.files?.find(f => f._id === activeFileId);

    // Track which file ID is loaded in the editor to prevent active-typing loops
    const [loadedFileId, setLoadedFileId] = useState(null);

    // When active file changes, load its content into the editor state
    useEffect(() => {
        if (project && activeFileId) {
            if (activeFileId !== loadedFileId) {
                const file = project.files?.find(f => f._id === activeFileId);
                if (file) {
                    let text = file.content || '';

                    // If it's not Markdown/TeX and doesn't look like HTML, normalize to HTML paragraphs for Quill
                    const isMarkdownOrTex = file.originalName.toLowerCase().endsWith('.md') || file.originalName.toLowerCase().endsWith('.tex');
                    if (!isMarkdownOrTex && text && !text.includes('<p>') && !text.includes('<h')) {
                        text = text.split('\n')
                            .map(line => line.trim())
                            .filter(line => line.length > 0)
                            .map(line => `<p>${line}</p>`)
                            .join('');
                    }

                    setLocalContent(text);
                    setLoadedFileId(activeFileId);
                }
            }
        }
    }, [activeFileId, project, loadedFileId]);

    const handleSaveContent = async (contentToSave) => {
        if (!activeFileId) return;
        setSaving(true);
        try {
            const token = localStorage.getItem('token');
            await axios.put(`${API_URL}/${id}/files/${activeFileId}`, { content: contentToSave }, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setProject(prev => {
                const updatedFiles = prev.files.map(f => f._id === activeFileId ? { ...f, content: contentToSave } : f);
                return { ...prev, files: updatedFiles };
            });
            if (!pendingRef.current) setDirty(false);
        } catch (error) {
            toast({ title: 'Save Failed', description: 'Could not sync changes to server.', variant: 'error' });
        } finally {
            setSaving(false);
        }
    };

    const handleEditorChange = (value) => {
        setLocalContent(value || '');
        setDirty(true);
        pendingRef.current = { id, fileId: activeFileId, content: value || '' };
        // Auto-save debounce (2 seconds)
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = setTimeout(() => {
            pendingRef.current = null;
            handleSaveContent(value || '');
        }, 2000);
    };

    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const ext = file.name.split('.').pop().toLowerCase();
        if (!['txt', 'md', 'doc', 'docx', 'tex'].includes(ext)) {
            toast({ title: 'Invalid format', description: 'Please upload only .txt, .md, .tex, or Word docs', variant: 'error' });
            return;
        }

        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const token = localStorage.getItem('token');
            const res = await axios.post(`${API_URL}/${id}/files`, formData, {
                headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' }
            });
            setProject(prev => ({ ...prev, files: [...prev.files, res.data] }));
            setActiveFileId(res.data._id);
            toast({ title: 'File uploaded', description: 'Document parsed successfully', variant: 'success' });
        } catch (error) {
            toast({ title: 'Upload failed', description: error.response?.data?.error || 'Could not parse document', variant: 'error' });
        } finally {
            setUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    // --- CRUD Handlers ---
    const handleProjectRenameSubmit = async () => {
        if (!editingProjectTitle.trim() || editingProjectTitle === project.title) {
            setIsEditingProject(false);
            return;
        }
        try {
            await renameProject.mutateAsync({ id, title: editingProjectTitle });
            setProject(prev => ({ ...prev, title: editingProjectTitle }));
            toast({ title: 'Project Renamed', variant: 'success' });
        } catch {
            toast({ title: 'Rename failed', variant: 'error' });
        }
        setIsEditingProject(false);
    };

    const handleProjectDelete = () => {
        confirm({
            title: "Delete Workspace",
            description: "Are you sure you want to permanently delete this entire project? This action cannot be undone.",
            confirmText: "Delete Project",
            onConfirm: async () => {
                try {
                    await deleteProject.mutateAsync(id);
                    toast({ title: 'Project Deleted', variant: 'success' });
                    navigate('/dashboard');
                } catch {
                    toast({ title: 'Deletion failed', variant: 'error' });
                }
            }
        });
    };

    const handleFileRenameSubmit = async (fileId) => {
        if (!editingFileName.trim()) {
            setEditingFileId(null);
            return;
        }
        try {
            const token = localStorage.getItem('token');
            const res = await axios.put(`${API_URL}/${id}/files/${fileId}/rename`, { originalName: editingFileName }, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setProject(prev => {
                const updatedFiles = prev.files.map(f => f._id === fileId ? { ...f, originalName: res.data.originalName } : f);
                return { ...prev, files: updatedFiles };
            });
            toast({ title: 'File Renamed', variant: 'success' });
        } catch (error) {
            toast({ title: 'Rename failed', variant: 'error' });
        } finally {
            setEditingFileId(null);
        }
    };

    const handleFileDelete = (fileId, e) => {
        e.stopPropagation();
        confirm({
            title: "Delete File",
            description: "Are you sure you want to delete this file?",
            confirmText: "Delete",
            onConfirm: async () => {
                try {
                    const token = localStorage.getItem('token');
                    await axios.delete(`${API_URL}/${id}/files/${fileId}`, {
                        headers: { Authorization: `Bearer ${token}` }
                    });
                    setProject(prev => ({ ...prev, files: prev.files.filter(f => f._id !== fileId) }));
                    if (activeFileId === fileId) {
                        const remainingFiles = project.files.filter(f => f._id !== fileId);
                        if (remainingFiles.length > 0) {
                            setActiveFileId(remainingFiles[0]._id);
                        } else {
                            setActiveFileId(null);
                            setLocalContent('');
                        }
                    }
                    toast({ title: 'File Deleted', variant: 'success' });
                } catch (error) {
                    toast({ title: 'Deletion failed', variant: 'error' });
                }
            }
        });
    };

    // ---- LaTeX Helpers ----
    useEffect(() => {
        if (!localContent || (!activeFile?.originalName.endsWith('.tex'))) { setLatexOutline([]); return; }
        const lines = localContent.split('\n');
        const newOutline = [];
        const sectionRegex = /^\\(sub)*section\*?\{([^}]+)\}/;
        lines.forEach((line, index) => {
            const match = line.trim().match(sectionRegex);
            if (match) {
                const level = match[1] ? match[1].length / 3 + 1 : 1;
                newOutline.push({ title: match[2], level, line: index + 1, id: `sec-${index}` });
            }
        });
        setLatexOutline(newOutline);
    }, [localContent, activeFile]);

    const sanitizeLatex = useCallback((code) => {
        if (!code || !code.trim()) {
            return `\\documentclass{article}\n\\begin{document}\nEmpty document\n\\end{document}`;
        }
        const trimmed = code.trim();
        // Already a full document → leave as-is.
        if (trimmed.includes("\\documentclass") && trimmed.includes("\\begin{document}")) {
            return trimmed;
        }
        // Has begin{document} but no documentclass → add only documentclass.
        if (trimmed.includes("\\begin{document}") && !trimmed.includes("\\documentclass")) {
            return `\\documentclass{article}\n${trimmed}`;
        }
        // Otherwise treat as raw content.
        return `\\documentclass{article}
\\usepackage[utf8]{inputenc}
\\usepackage[T1]{fontenc}
\\usepackage{lmodern}
\\usepackage{hyperref}
\\begin{document}
${trimmed}
\\end{document}`;
    }, []);

    // Format this document via the Deep Scan engine (the single document→LaTeX flow).
    const handleFormatInDeepScan = () => {
        setDeepScanProjectId(id);
        setDeepScanSourceFileName(activeFile?.originalName?.replace(/\.[^.]+$/, '') || '');
        navigate('/deep-scan');
    };

    const compileLatex = useCallback(async () => {
        setLatexCompiling(true);
        setLatexCompiled(false);
        try {
            const response = await fetch(ENDPOINTS.deepScanCompile, {
                method: "POST",
                headers: authHeaders({ "Content-Type": "application/json" }),
                body: JSON.stringify({ latex: sanitizeLatex(localContent), job: null }),
            });

            const iframe = document.querySelector('iframe[name="latex-pdf-preview-ws"]');

            if (!response.ok) {
                let errorMessage = "Compilation failed";
                try {
                    const data = await response.json();
                    // the tectonic log is the actionable part of a 422
                    errorMessage = data?.log || data?.error || data?.message || errorMessage;
                } catch {
                    errorMessage = await response.text();
                }
                if (iframe) {
                    iframe.srcdoc = `
                        <div style="font-family: Arial, sans-serif; padding: 20px; background: #fff7f7; color: #7f1d1d; height: 100%; box-sizing: border-box;">
                            <h2 style="margin-top:0;">Compilation Error</h2>
                            <pre style="white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.5;">${String(errorMessage)
                                .replace(/&/g, "&amp;")
                                .replace(/</g, "&lt;")
                                .replace(/>/g, "&gt;")}</pre>
                        </div>
                    `;
                }
                throw new Error(errorMessage);
            }

            const blob = await response.blob();
            const pdfUrl = URL.createObjectURL(blob);
            if (iframe) iframe.src = pdfUrl;

            setLatexCompiled(true);
            toast({ title: "Compilation successful", description: "PDF preview updated.", variant: "success" });
        } catch (err) {
            console.error("LaTeX Compilation Error:", err);
            toast({ title: "Compilation failed", description: String(err.message || "Could not compile LaTeX").slice(0, 200), variant: "error" });
        } finally {
            setLatexCompiling(false);
        }
    }, [localContent, sanitizeLatex, toast]);

    // -----------------------------------------
    if (loading) {
        return <div className="flex h-full items-center justify-center p-8"><Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary-500)]" /></div>;
    }

    if (!project) return <div>Workspace not found.</div>;

    return (
        <div className="flex h-full w-full bg-white rounded-[var(--radius-xl)] shadow-[var(--shadow-card)] overflow-hidden border border-[var(--color-surface-200)]">

            <FileTree
                project={project}
                activeFileId={activeFileId}
                setActiveFileId={setActiveFileId}
                uploading={uploading}
                fileInputRef={fileInputRef}
                isEditingProject={isEditingProject}
                setIsEditingProject={setIsEditingProject}
                editingProjectTitle={editingProjectTitle}
                setEditingProjectTitle={setEditingProjectTitle}
                editingFileId={editingFileId}
                setEditingFileId={setEditingFileId}
                editingFileName={editingFileName}
                setEditingFileName={setEditingFileName}
                onProjectRename={handleProjectRenameSubmit}
                onProjectDelete={handleProjectDelete}
                onFileRename={handleFileRenameSubmit}
                onFileDelete={handleFileDelete}
                onFileUpload={handleFileUpload}
            />

            {/* Main Area */}
            <div className="flex-1 flex flex-col bg-white overflow-hidden relative">

                {activeFile && (
                    <div className="h-full flex flex-col overflow-hidden">
                        <div className="px-6 py-4 border-b border-[var(--color-surface-200)] flex justify-between items-center bg-white z-10">
                            <div className="flex items-center gap-3">
                                <h3 className="text-xl font-bold font-karla text-[var(--color-text-main)]">{activeFile.originalName}</h3>
                                {activeFile.originalName.endsWith('.tex') && (
                                    <Button
                                        variant="primary"
                                        onClick={compileLatex}
                                        disabled={latexCompiling}
                                        className="h-8 px-4 text-xs font-semibold"
                                    >
                                        {latexCompiling ? (
                                            <><span className="mr-1.5 h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />Compiling...</>
                                        ) : (
                                            <><Play className="h-3.5 w-3.5 mr-1.5 fill-current" />Compile PDF</>
                                        )}
                                    </Button>
                                )}
                                <button
                                    onClick={handleFormatInDeepScan}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-white bg-[var(--color-primary-600)] hover:bg-[var(--color-primary-900)] rounded-lg shadow-sm transition-colors"
                                    title="Format this document with the Deep Scan engine"
                                >
                                    <Microscope className="w-3.5 h-3.5" />
                                    Format (Deep Scan)
                                </button>
                            </div>
                            <div className="flex items-center gap-2 text-xs font-bold text-[var(--color-text-muted)]">
                                {saving ? <><Loader2 className="w-4 h-4 animate-spin" /> Saving...</>
                                    : dirty ? <><Save className="w-4 h-4 text-amber-500" /> Unsaved changes</>
                                        : <><Save className="w-4 h-4 text-green-600" /> Saved</>}
                            </div>
                        </div>

                        <div className="flex-1 overflow-hidden relative" data-color-mode="light">
                            {loadedFileId !== activeFile._id ? (
                                <div className="h-full w-full flex items-center justify-center p-8 bg-[var(--color-surface-50)]">
                                    <div className="flex flex-col items-center gap-3">
                                        <Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary-500)]" />
                                        <p className="text-sm font-medium text-[var(--color-text-muted)] animate-pulse">Hydrating editor...</p>
                                    </div>
                                </div>
                            ) : activeFile.originalName.endsWith('.tex') ? (
                                <LatexEditorPane
                                    activeFile={activeFile}
                                    localContent={localContent}
                                    onEditorChange={handleEditorChange}
                                    latexOutline={latexOutline}
                                    latexEditorRef={latexEditorRef}
                                    latexPreviewRef={latexPreviewRef}
                                    latexCompiling={latexCompiling}
                                    latexCompiled={latexCompiled}
                                />
                            ) : activeFile.originalName.endsWith('.md') ? (
                                // Markdown Split Editor
                                <div className="h-full w-full custom-md-editor">
                                    <style>{`
                                        .w-md-editor { height: 100% !important; border-radius: 0; border: none; }
                                        .w-md-editor-toolbar { padding: 8px 16px; background: var(--color-surface-50); border-bottom: 1px solid var(--color-surface-200); }
                                    `}</style>
                                    <MDEditor
                                        value={localContent}
                                        onChange={handleEditorChange}
                                        preview="live"
                                        height="100%"
                                        className="h-full w-full border-0"
                                    />
                                </div>
                            ) : (
                                // Rich Text Editor (React-Quill)
                                <div className="h-full w-full flex flex-col p-4 overflow-y-auto bg-[var(--color-surface-50)]">
                                    <div className="bg-white max-w-4xl mx-auto w-full min-h-[800px] shadow-sm border border-[var(--color-surface-200)] pb-12">
                                        <style>{`
                                            .ql-toolbar.ql-snow { border: none; border-bottom: 1px solid var(--color-surface-200); padding: 12px 24px; background: #fafafa; position: sticky; top: 0; z-index: 10; }
                                            .ql-container.ql-snow { border: none !important; font-family: 'DM Sans', sans-serif; font-size: 16px; }
                                            .ql-editor { padding: 48px 64px; min-height: 800px; color: var(--color-text-main); }
                                            .ql-editor p { margin-bottom: 1em; line-height: 1.6; }
                                            .ql-editor h1, .ql-editor h2, .ql-editor h3 { font-family: 'Karla', sans-serif; font-weight: bold; margin-bottom: 0.5em; margin-top: 1em; color: var(--color-primary-900); }
                                        `}</style>
                                        <ReactQuill
                                            theme="snow"
                                            value={localContent}
                                            onChange={handleEditorChange}
                                            className="h-full"
                                            modules={{
                                                toolbar: [
                                                    [{ 'header': [1, 2, 3, false] }],
                                                    ['bold', 'italic', 'underline', 'strike'],
                                                    [{ 'list': 'ordered' }, { 'list': 'bullet' }],
                                                    ['clean']
                                                ]
                                            }}
                                        />
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {project.files?.length === 0 && (
                    <EmptyState uploading={uploading} onClick={() => fileInputRef.current?.click()} />
                )}
            </div>
        </div>
    );
}

// Keyed by project id: /project/A -> /project/B is the same route, so without
// a remount B inherited A's file selection (an id B doesn't have) and showed
// an empty editor.
export function ProjectWorkspace() {
    const { id } = useParams();
    return <ProjectWorkspaceInner key={id} />;
}

export default ProjectWorkspace;
