// Step 5 — Agent: the final LaTeX (including any edits made in step 4) is
// converted server-side into a DOCX styled like the compiled PDF. That DOCX is
// what is previewed here, downloaded, and handed to the AI document agent.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Download, FileText, ChevronLeft, RotateCcw, Loader2, Sparkles } from 'lucide-react';
import * as docx from 'docx-preview';
import toast from 'react-hot-toast';
import useDeepScanStore from '../../store/useDeepScanStore';
import { authHeaders } from '../../config/api';
import { deepScanService } from '../../services';

export function AgentStep() {
  const { latexContent, jobId, targetStyle, uploadedFile, resetPipeline, setStep } = useDeepScanStore();
  const navigate = useNavigate();
  const previewRef = useRef(null);
  // 'converting' -> 'rendering' -> 'ready' | 'error'
  const [status, setStatus] = useState('converting');
  const [error, setError] = useState('');
  const [docxName, setDocxName] = useState(null);
  const [attempt, setAttempt] = useState(0);

  const fetchDocx = useCallback(async (name) => {
    const res = await fetch(deepScanService.downloadUrl(encodeURIComponent(name)), { headers: authHeaders() });
    if (!res.ok) throw new Error(`Could not fetch the document (${res.status})`);
    return res.blob();
  }, []);

  useEffect(() => {
    if (!latexContent) return;   // shown as an error below, nothing to convert
    let cancelled = false;
    (async () => {
      try {
        const { filename } = await deepScanService.latexToDocx(latexContent, {
          job: jobId,
          style: targetStyle,
          name: uploadedFile?.name,
        });
        if (cancelled) return;
        setDocxName(filename);
        setStatus('rendering');
        const blob = await fetchDocx(filename);
        if (cancelled || !previewRef.current) return;
        previewRef.current.innerHTML = '';
        await docx.renderAsync(blob, previewRef.current, previewRef.current, {
          className: 'docx',
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          breakPages: true,
          ignoreLastRenderedPageBreak: true,
          trimXmlDeclaration: true,
        });
        if (!cancelled) setStatus('ready');
      } catch (err) {
        if (cancelled) return;
        console.error('Agent step:', err);
        setError(err?.message || 'The preview could not be generated.');
        setStatus('error');
      }
    })();
    return () => { cancelled = true; };
  }, [latexContent, jobId, targetStyle, uploadedFile, fetchDocx, attempt]);

  const download = async () => {
    try {
      const blob = await fetchDocx(docxName);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = docxName; a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err.message || 'Download failed');
    }
  };

  // With no LaTeX there is nothing to convert: show that instead of a spinner.
  const effectiveStatus = latexContent ? status : 'error';
  const effectiveError = latexContent ? error : 'There is no LaTeX yet. Run the pipeline first.';
  const busy = effectiveStatus === 'converting' || effectiveStatus === 'rendering';

  return (
    <div className="flex flex-col h-full bg-[var(--color-surface-50)]">
      <div className="px-6 py-4 bg-white border-b border-[var(--color-surface-200)] flex items-center justify-between shrink-0 z-10">
        <div>
          <h2 className="text-3xl font-anton font-normal tracking-wide text-[var(--color-text-main)] flex items-center gap-2">
            <Bot className="w-7 h-7 text-[var(--color-primary-600)]" /> AI Document Agent
          </h2>
          <p className="text-sm font-medium text-[var(--color-text-muted)] mt-1">
            Your final document, generated from the LaTeX. Download it, or open it in the AI agent to keep editing.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {docxName && effectiveStatus !== 'converting' && (
            <>
              <button
                onClick={() => navigate('/advance-workshop', { state: { file: docxName } })}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg border border-[var(--color-primary-300)] text-[var(--color-primary-700)] bg-[var(--color-primary-50)] hover:bg-[var(--color-primary-100)] shadow-sm transition-colors"
              >
                <Sparkles className="w-4 h-4" /> Open in AI Agent
              </button>
              <button
                onClick={download}
                className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-[var(--color-primary-600)] text-white hover:bg-[var(--color-primary-700)] shadow-sm transition-transform hover:scale-105"
              >
                <Download className="w-4 h-4" /> Download DOCX
              </button>
            </>
          )}
          {latexContent && (
            <button
              onClick={() => {
                const blob = new Blob([latexContent], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'output.tex'; a.click();
                URL.revokeObjectURL(url);
              }}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg border border-[var(--color-surface-300)] text-[var(--color-text-main)] bg-white hover:bg-[var(--color-surface-50)] shadow-sm transition-colors"
            >
              <FileText className="w-4 h-4" /> Download LaTeX
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden relative justify-center">
        <div className="flex-1 overflow-y-auto w-full flex flex-col items-center py-8 px-4 h-full bg-[var(--color-surface-50)]">
          <style>{`
             .docx-wrapper { background: transparent !important; padding: 0 !important; display: flex; flex-direction: column; align-items: center; gap: 2rem; width: 100%; }
             .docx-wrapper > section.docx { background: white !important; box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1) !important; border-radius: 2px !important; margin-bottom: 0 !important; border: 1px solid var(--color-surface-300) !important; }
             .docx-wrapper > section.docx * { word-break: break-word; }
             .docx-wrapper > section.docx table { width: 100% !important; table-layout: fixed; }
          `}</style>

          <div className="w-full max-w-[900px] mb-8 relative flex flex-col items-center min-h-[600px]">
            {busy && (
              <div className="flex flex-col items-center justify-center gap-3 py-32 text-[var(--color-text-muted)]">
                <Loader2 className="w-8 h-8 animate-spin" />
                <p className="text-sm font-medium">
                  {effectiveStatus === 'converting' ? 'Building the DOCX from your LaTeX…' : 'Rendering preview…'}
                </p>
              </div>
            )}
            {effectiveStatus === 'error' && (
              <div className="w-full flex flex-col items-center justify-center text-[var(--color-text-muted)] bg-white shadow-xl border border-[var(--color-surface-300)] rounded-[2px] py-24 px-8 mt-4 max-w-[816px] text-center">
                <FileText className="w-16 h-16 opacity-30 mb-4" />
                <p className="text-lg font-semibold text-[var(--color-text-main)]">The preview could not be generated.</p>
                <p className="text-sm mt-2 max-w-[560px] break-words">{effectiveError}</p>
                {latexContent && (
                  <button
                    onClick={() => { setStatus('converting'); setAttempt((n) => n + 1); }}
                    className="mt-6 flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-[var(--color-primary-600)] text-white hover:bg-[var(--color-primary-700)]"
                  >
                    <RotateCcw className="w-4 h-4" /> Try again
                  </button>
                )}
              </div>
            )}
            {/* kept mounted so docx-preview always has a target */}
            <div ref={previewRef} className={effectiveStatus === 'ready' || effectiveStatus === 'rendering' ? 'w-full' : 'hidden'} />
          </div>

          <div className="flex justify-center gap-4 mb-8 w-full max-w-[850px]">
            <button onClick={() => setStep(4)} className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-xl border border-[var(--color-surface-300)] text-[var(--color-text-main)] bg-white hover:bg-[var(--color-surface-50)] shadow-sm">
              <ChevronLeft className="w-4 h-4" /> Back to LaTeX Editor
            </button>
            <button
              onClick={resetPipeline}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-xl border border-[var(--color-primary-300)] text-[var(--color-primary-700)] bg-[var(--color-primary-50)] hover:bg-[var(--color-primary-100)] shadow-sm transition-colors"
            >
              <RotateCcw className="w-4 h-4" /> Format Another Document
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
