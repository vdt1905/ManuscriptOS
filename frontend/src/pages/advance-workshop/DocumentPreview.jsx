// Center panel — live DOCX HTML preview (presentational).
import { FileText, Download, RefreshCw, Loader2, AlertTriangle } from 'lucide-react';
import { Button } from '../../components/Button';

export function DocumentPreview({
  selectedFile, previewHtml, previewLoading, previewError,
  onDownload, onDownloadPdf, exportingPdf, onRefresh,
}) {
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#f8fafc]">
      {/* Preview Header */}
      <div className="px-6 py-3.5 bg-white border-b border-[var(--color-surface-200)] flex items-center justify-between shrink-0 shadow-sm z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2 bg-gradient-to-br from-[var(--color-primary-100)] to-[var(--color-primary-50)] rounded-xl">
            <FileText className="w-6 h-6 text-[var(--color-primary-600)]" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-[var(--color-text-main)] flex items-center gap-2">
              Document Preview
            </h2>
            <p className="text-[11px] text-[var(--color-text-muted)] truncate font-medium">
              {selectedFile || 'No file selected'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {selectedFile && (
            <>
              <Button variant="secondary" size="sm" onClick={onDownload} className="h-9 gap-2 text-xs font-semibold px-4">
                <Download className="w-4 h-4" />
                DOCX
              </Button>
              <Button variant="secondary" size="sm" onClick={onDownloadPdf} disabled={exportingPdf} className="h-9 gap-2 text-xs font-semibold px-4">
                {exportingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                {exportingPdf ? 'Exporting…' : 'PDF'}
              </Button>
            </>
          )}
          <Button
            variant="primary" size="sm"
            onClick={() => onRefresh()}
            disabled={!selectedFile || previewLoading}
            className="h-9 gap-2 text-xs font-semibold px-4"
          >
            <RefreshCw className={`w-4 h-4 ${previewLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Preview Body */}
      <div className="flex-1 overflow-y-auto p-10 relative min-h-0 scroll-smooth">
        {/* Loading overlay */}
        {previewLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/60 backdrop-blur-sm z-10">
            <div className="flex flex-col items-center gap-4 bg-white p-10 rounded-2xl shadow-2xl border border-[var(--color-surface-200)]">
              <Loader2 className="w-12 h-12 animate-spin text-[var(--color-primary-500)]" />
              <span className="font-bold text-sm text-[var(--color-text-main)] animate-pulse tracking-wide uppercase">Updating Preview…</span>
            </div>
          </div>
        )}

        {!selectedFile ? (
          <div className="h-full flex flex-col items-center justify-center text-[var(--color-text-muted)] opacity-60">
            <div className="w-24 h-24 rounded-full bg-[var(--color-surface-100)] flex items-center justify-center mb-6 border border-[var(--color-surface-200)]">
              <FileText className="w-12 h-12 text-[var(--color-surface-300)]" strokeWidth={1} />
            </div>
            <p className="font-bold text-lg mb-1">Interactive Workspace</p>
            <p className="text-sm">Select a document from the right to begin editing.</p>
          </div>
        ) : previewError ? (
          <div className="max-w-lg mx-auto mt-20">
            <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center shadow-md">
              <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
              <p className="text-red-800 font-bold text-lg mb-2">Could Not Load Preview</p>
              <p className="text-sm text-red-600 leading-relaxed font-medium">{previewError}</p>
            </div>
          </div>
        ) : previewHtml ? (
          <div
            className="bg-white mx-auto rounded-lg shadow-2xl border border-[var(--color-surface-200)] transition-all duration-500"
            style={{
              maxWidth: 850,
              padding: '80px 80px 100px',
              minHeight: 1100,
              opacity: previewLoading ? 0.3 : 1,
              transform: previewLoading ? 'scale(0.98)' : 'scale(1)',
            }}
            dangerouslySetInnerHTML={{ __html: previewHtml }}
          />
        ) : null}
      </div>
    </div>
  );
}
