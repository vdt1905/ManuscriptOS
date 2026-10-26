// AdvanceWorkspace — DocBot agent workspace (Track A5 decomposition).
// This component owns ALL state + handlers (the orchestrator); the three panels
// (chat / preview / library) are presentational components under ./advance-workshop/.
import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { useLocation } from 'react-router-dom';
import { ENDPOINTS } from '../config/api';
import { useDocuments } from '../hooks/queries/useDocuments';
import { useToast } from '../components/Toasts';
import { DocBotChat } from './advance-workshop/DocBotChat';
import { DocumentPreview } from './advance-workshop/DocumentPreview';
import { DocumentLibrary } from './advance-workshop/DocumentLibrary';

const API_BASE = ENDPOINTS.fileEditor;

export function AdvanceWorkspace() {
    const { toast } = useToast();
    /* ── State ── */
    const [sessionId] = useState(() =>
        localStorage.getItem('agentSessionId') || `ui-${Math.random().toString(36).substr(2, 9)}`
    );
    const { data: docs = [], refetch: refetchDocuments, isError: docsError } = useDocuments();

    // Surface a doc-list load failure (previously a silent console.error).
    useEffect(() => {
        if (docsError) {
            toast({ title: 'Could not load documents', description: 'Check your connection and try again.', variant: 'error' });
        }
    }, [docsError, toast]);
    // A document handed over from Deep Scan ("Open in AI Agent") starts selected.
    const location = useLocation();
    const handoff = location.state?.file ?? null;
    const [selectedFile, setSelectedFile] = useState(handoff);
    const [uploading, setUploading] = useState(false);
    const [deleting, setDeleting] = useState(null);

    const [chatInput, setChatInput] = useState('');
    const [chatHistory, setChatHistory] = useState(() => {
        const saved = localStorage.getItem('agentChatHistory');
        if (saved) { try { return JSON.parse(saved); } catch (e) { /* noop */ } }
        return [{
            id: 'init', role: 'bot',
            text: "Hi! I'm DocBot 🤖 — Tell me what you'd like to change in your documents!",
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }];
    });
    const [isSending, setIsSending] = useState(false);

    const [previewHtml, setPreviewHtml] = useState(null);
    const [previewLoading, setPreviewLoading] = useState(Boolean(handoff));
    const [previewError, setPreviewError] = useState(null);

    const chatScrollRef = useRef(null);
    const fileInputRef = useRef(null);

    /* ── Persist chat + session to localStorage ── */
    useEffect(() => {
        localStorage.setItem('agentChatHistory', JSON.stringify(chatHistory));
        localStorage.setItem('agentSessionId', sessionId);
    }, [chatHistory, sessionId]);

    /* ── Docs come from React Query (useDocuments); refetchDocuments() after
          upload/delete/chat-edit. ── */

    useEffect(() => {
        if (chatScrollRef.current)
            chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }, [chatHistory, isSending]);

    /* ── File Selection ── */
    const handleSelectFile = (filename, corrupted) => {
        if (corrupted) return;          // don't select corrupted files
        setSelectedFile(filename);
        setChatInput('');
        refreshPreview(filename);
    };

    // Arriving from Deep Scan's "Open in AI Agent": select that document.
    /* ── Preview ── */
    const refreshPreview = async (name = selectedFile) => {
        if (!name) return;
        setPreviewLoading(true);
        setPreviewError(null);
        await loadPreview(name);
    };

    const loadPreview = async (name) => {
        try {
            const res = await axios.get(`${API_BASE}/documents/${encodeURIComponent(name)}/preview`, { responseType: 'text' });
            setPreviewHtml(res.data);
        } catch (e) {
            const detail = e.response?.data?.detail || e.response?.statusText || e.message;
            setPreviewError(detail);
        } finally {
            setPreviewLoading(false);
        }
    };

    // Load the preview of a handed-over document (selected in initial state).
    useEffect(() => {
        if (handoff) loadPreview(handoff);
    }, [handoff]);

    /* ── Upload ── */
    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);
        try {
            // PDFs are converted server-side (a few seconds per 10 pages)
            const res = await axios.post(`${API_BASE}/documents/upload`, formData, { timeout: 300000 });
            if (res.data?.filename) {
                await refetchDocuments();
                handleSelectFile(res.data.filename, false);
                if (res.data.converted_from === 'pdf') {
                    toast({ title: 'PDF converted', description: `DocBot can now edit ${res.data.filename}. Use the PDF button to export it back.`, variant: 'success' });
                }
            }
        } catch (err) {
            alert('Upload Error: ' + (err.response?.data?.detail || err.message));
        } finally {
            setUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    /* ── Download ── */
    // fetch rather than navigate: a plain navigation cannot send the auth
    // header, and on failure it replaced the whole app with a JSON error page
    const downloadAs = async (format) => {
        const stem = selectedFile.replace(/\.docx$/i, '');
        const res = await axios.get(
            `${API_BASE}/documents/${encodeURIComponent(selectedFile)}/download`,
            { params: { format }, responseType: 'blob', timeout: 300000 },
        );
        const url = URL.createObjectURL(res.data);
        const a = document.createElement('a');
        a.href = url; a.download = format === 'pdf' ? `${stem}.pdf` : selectedFile; a.click();
        URL.revokeObjectURL(url);
    };

    const handleDownload = async () => {
        if (!selectedFile) return;
        try {
            await downloadAs('docx');
        } catch (e) {
            toast({ title: 'Download failed', description: e.response?.statusText || e.message, variant: 'error' });
        }
    };

    const [exportingPdf, setExportingPdf] = useState(false);
    const handleDownloadPdf = async () => {
        if (!selectedFile) return;
        setExportingPdf(true);
        try {
            await downloadAs('pdf');
        } catch (e) {
            // the error body is a Blob here; read the server's message out of it
            let detail = e.message;
            try { detail = JSON.parse(await e.response.data.text()).detail || detail; } catch { /* keep e.message */ }
            toast({ title: 'PDF export failed', description: detail, variant: 'error' });
        } finally {
            setExportingPdf(false);
        }
    };

    /* ── Delete ── */
    const handleDeleteDocument = async (e, filename) => {
        e.stopPropagation();
        if (!window.confirm(`Delete "${filename}"?`)) return;
        setDeleting(filename);
        try {
            await axios.delete(`${API_BASE}/documents/${encodeURIComponent(filename)}`);
            if (selectedFile === filename) {
                setSelectedFile(null);
                setPreviewHtml(null);
            }
            await refetchDocuments();
        } catch (err) {
            alert('Delete Error: ' + (err.response?.data?.detail || err.message));
        } finally {
            setDeleting(null);
        }
    };

    /* ── Clear Chat ── */
    const handleClearChat = () => {
        setChatHistory([{
            id: 'init', role: 'bot',
            text: "Chat cleared! 🧹 Tell me what to do.",
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }]);
    };

    /* ── Chat ── */
    const handleSendMessage = async () => {
        const text = chatInput.trim();
        if (!text) return;

        const userMsg = {
            id: Date.now().toString(), role: 'user', text,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        setChatHistory(prev => [...prev, userMsg]);
        setChatInput('');
        setIsSending(true);

        const msgPayload = selectedFile ? `[Working on file: ${selectedFile}]\n\n${text}` : text;

        try {
            const res = await axios.post(`${API_BASE}/chat`, {
                message: msgPayload, user_id: 'local_ui_user', session_id: sessionId
            }, { timeout: 45000 });

            let responseText = res.data?.response || 'No response generated.';
            responseText = responseText
                .replace(/\n\n/g, '<br><br>')
                .replace(/\n/g, '<br>')
                .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
                .replace(/\*(.*?)\*/g, '<i>$1</i>')
                .replace(/`(.*?)`/g, '<code style="background:#f1f5f9;padding:1px 5px;border-radius:4px;font-size:12px;">$1</code>');

            setChatHistory(prev => [...prev, {
                id: Date.now().toString(), role: 'bot', textHtml: responseText,
                time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }]);

            await refetchDocuments();
            if (selectedFile) setTimeout(() => refreshPreview(selectedFile), 600);
        } catch (err) {
            const errMsg = err.code === 'ECONNABORTED' ? 'Request timed out' : err.message;
            setChatHistory(prev => [...prev, {
                id: Date.now().toString(), role: 'bot',
                textHtml: `<span style="color:#ef4444;font-weight:600;">⚠️ ${errMsg}</span>`,
                time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }]);
        } finally {
            setIsSending(false);
        }
    };

    /* ═══════════════ RENDER ═══════════════ */
    return (
        <div className="flex h-[calc(100vh-120px)] rounded-2xl overflow-hidden border border-[var(--color-surface-200)] shadow-lg bg-white">
            <DocBotChat
                chatHistory={chatHistory}
                isSending={isSending}
                chatInput={chatInput}
                setChatInput={setChatInput}
                selectedFile={selectedFile}
                chatScrollRef={chatScrollRef}
                onClearChat={handleClearChat}
                onSendMessage={handleSendMessage}
            />
            <DocumentPreview
                selectedFile={selectedFile}
                previewHtml={previewHtml}
                previewLoading={previewLoading}
                previewError={previewError}
                onDownload={handleDownload}
                onDownloadPdf={handleDownloadPdf}
                exportingPdf={exportingPdf}
                onRefresh={refreshPreview}
            />
            <DocumentLibrary
                docs={docs}
                selectedFile={selectedFile}
                uploading={uploading}
                deleting={deleting}
                fileInputRef={fileInputRef}
                onUpload={handleFileUpload}
                onSelectFile={handleSelectFile}
                onDeleteDocument={handleDeleteDocument}
            />
        </div>
    );
}

export default AdvanceWorkspace;
