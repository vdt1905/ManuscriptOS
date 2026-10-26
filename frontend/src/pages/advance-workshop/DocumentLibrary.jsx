// Right panel — documents library + upload (presentational).
import { File, FileText, Upload, Loader2, Trash2, AlertTriangle } from 'lucide-react';
import { formatBytes, timeAgo } from './helpers';

export function DocumentLibrary({
  docs, selectedFile, uploading, deleting, fileInputRef,
  onUpload, onSelectFile, onDeleteDocument,
}) {
  return (
    <div className="w-[280px] shrink-0 flex flex-col border-l border-[var(--color-surface-200)] bg-white min-h-0">
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between bg-gradient-to-r from-[var(--color-primary-600)] to-[var(--color-primary-500)] text-white shrink-0">
        <h3 className="text-[13px] font-bold flex items-center gap-2 tracking-wide uppercase">
          <File className="w-4 h-4 opacity-80" />
          Documents
        </h3>
        <span className="text-[11px] font-bold bg-white/20 px-2.5 py-1 rounded-full">{docs.length}</span>
      </div>

      {/* Upload Section */}
      <div className="px-4 pt-4 pb-2 shrink-0 border-b border-[var(--color-surface-200)]">
        <label className={`flex flex-col items-center justify-center gap-2 w-full p-4 text-xs font-bold rounded-xl border-2 border-dashed transition-all cursor-pointer shadow-sm mb-3
          ${uploading
            ? 'border-[var(--color-primary-300)] bg-[var(--color-primary-50)] text-[var(--color-primary-600)] cursor-wait'
            : 'border-[var(--color-surface-300)] bg-[var(--color-surface-50)] text-[var(--color-text-muted)] hover:border-[var(--color-primary-400)] hover:bg-[var(--color-primary-50)] hover:text-[var(--color-primary-600)]'
          }`}
        >
          {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5 opacity-60" />}
          <span className="mt-1">{uploading ? 'UPLOADING…' : 'UPLOAD .DOCX OR .PDF'}</span>
          {!uploading && (
            <span className="text-[10px] font-medium normal-case opacity-80">PDFs are converted so DocBot can edit them</span>
          )}
          <input type="file" className="hidden" accept=".docx,.pdf" onChange={onUpload} ref={fileInputRef} disabled={uploading} />
        </label>
      </div>

      {/* File List */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 pt-2 space-y-2 min-h-0 scroll-smooth">
        {docs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-[var(--color-text-muted)]">
            <div className="w-16 h-16 rounded-full bg-[var(--color-surface-50)] flex items-center justify-center mb-4 opacity-50">
              <FileText className="w-8 h-8" />
            </div>
            <p className="text-xs font-semibold uppercase tracking-wider">Empty Library</p>
          </div>
        ) : docs.map(doc => {
          const isActive = selectedFile === doc.filename;
          const isCorrupted = doc.corrupted;
          return (
            <div
              key={doc.filename}
              onClick={() => onSelectFile(doc.filename, isCorrupted)}
              className={`group flex items-center gap-3 px-3 py-3 rounded-xl transition-all text-left relative overflow-hidden border
                ${isCorrupted
                  ? 'opacity-60 cursor-not-allowed bg-red-50/30 border-red-100'
                  : isActive
                    ? 'bg-[var(--color-primary-50)] border-[var(--color-primary-200)] shadow-md ring-1 ring-[var(--color-primary-100)]'
                    : 'hover:bg-[var(--color-surface-50)] cursor-pointer border-transparent hover:border-[var(--color-surface-200)] shadow-sm'
                }`}
            >
              {/* Icon */}
              <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center shadow-inner transition-colors ${isCorrupted ? 'bg-red-50' : isActive ? 'bg-white' : 'bg-[var(--color-surface-100)]'
                }`}>
                {isCorrupted
                  ? <AlertTriangle className="w-5 h-5 text-red-500" />
                  : <FileText className={`w-5 h-5 ${isActive ? 'text-[var(--color-primary-600)]' : 'text-[var(--color-text-muted)]'}`} />}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className={`text-[13px] font-bold truncate tracking-tight mb-0.5 ${isCorrupted ? 'text-red-700 line-through opacity-70' : isActive ? 'text-[var(--color-primary-800)]' : 'text-[var(--color-text-main)]'
                  }`}>{doc.filename}</p>
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md ${isActive ? 'bg-[var(--color-primary-100)] text-[var(--color-primary-700)]' : 'bg-[var(--color-surface-200)] text-[var(--color-text-muted)]'
                    }`}>
                    {formatBytes(doc.size_bytes)}
                  </span>
                  <span className="text-[10px] font-medium text-[var(--color-text-muted)]">
                    {timeAgo(doc.modified)}
                  </span>
                </div>
              </div>

              {/* Delete */}
              <button
                onClick={(e) => onDeleteDocument(e, doc.filename)}
                disabled={deleting === doc.filename}
                className="shrink-0 p-2 rounded-lg text-slate-300 opacity-0 group-hover:opacity-100 hover:bg-red-50 hover:text-red-500 transition-all border border-transparent hover:border-red-100"
                title="Delete"
              >
                {deleting === doc.filename
                  ? <Loader2 className="w-4 h-4 animate-spin text-red-500" />
                  : <Trash2 className="w-4 h-4" />}
              </button>

              {/* Corrupted Label */}
              {isCorrupted && (
                <div className="absolute top-0 right-0 py-0.5 px-2 bg-red-500 text-[8px] font-black text-white uppercase tracking-tighter rounded-bl-lg">
                  Corrupted
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
