// Left sidebar — project title + file list + add-file (presentational).
import { Link } from 'react-router-dom';
import { FileText, FileType2, Code2, Loader2, Plus, ChevronLeft, Trash2, Edit2, Check, X } from 'lucide-react';
import { Button, cn } from '../../components/Button';

export function FileTree({
  project, activeFileId, setActiveFileId, uploading, fileInputRef,
  isEditingProject, setIsEditingProject, editingProjectTitle, setEditingProjectTitle,
  editingFileId, setEditingFileId, editingFileName, setEditingFileName,
  onProjectRename, onProjectDelete, onFileRename, onFileDelete, onFileUpload,
}) {
  return (
    <div className="w-64 border-r border-[var(--color-surface-200)] bg-[var(--color-surface-50)] flex flex-col">
      <div className="p-4 border-b border-[var(--color-surface-200)] pb-4 shadow-sm bg-white z-10 flex flex-col gap-3">
        <Link to="/dashboard" className="flex items-center gap-1 text-xs font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-primary-600)] transition-colors w-max">
          <ChevronLeft className="w-4 h-4" /> Back to Dashboard
        </Link>

        <div className="flex items-start justify-between group">
          {isEditingProject ? (
            <div className="flex items-center gap-1 w-full bg-[var(--color-surface-100)] p-1 rounded border border-[var(--color-primary-300)]">
              <input
                autoFocus
                className="w-full bg-transparent text-sm font-bold text-[var(--color-text-main)] outline-none px-1"
                value={editingProjectTitle}
                onChange={(e) => setEditingProjectTitle(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && onProjectRename()}
              />
              <button onClick={onProjectRename} className="p-1 hover:bg-green-100 text-green-700 rounded"><Check className="w-3 h-3" /></button>
              <button onClick={() => setIsEditingProject(false)} className="p-1 hover:bg-red-100 text-red-700 rounded"><X className="w-3 h-3" /></button>
            </div>
          ) : (
            <>
              <h2
                className="font-bold text-[var(--color-text-main)] truncate cursor-pointer hover:text-[var(--color-primary-600)]"
                title="Click to rename"
                onClick={() => { setEditingProjectTitle(project.title); setIsEditingProject(true); }}
              >
                {project.title}
              </h2>
              <button
                onClick={onProjectDelete}
                className="opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:bg-red-50 rounded transition-all shrink-0 ml-2"
                title="Delete Project"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
        {project.files?.map((file) => (
          <div
            key={file._id}
            className={cn(
              "group flex items-center justify-between p-2 rounded-lg text-sm transition-colors w-full cursor-pointer",
              activeFileId === file._id
                ? "bg-[var(--color-primary-100)] text-[var(--color-primary-900)] font-bold"
                : "text-[var(--color-text-main)] hover:bg-[var(--color-surface-100)]"
            )}
            onClick={() => { if (editingFileId !== file._id) setActiveFileId(file._id); }}
          >
            <div className="flex items-center gap-2 overflow-hidden flex-1">
              {file.originalName.endsWith('.md') ? <FileType2 className="w-4 h-4 shrink-0 text-blue-500" /> : file.originalName.endsWith('.tex') ? <Code2 className="w-4 h-4 shrink-0 text-[var(--color-primary-500)]" /> : <FileText className="w-4 h-4 shrink-0 opacity-70" />}

              {editingFileId === file._id ? (
                <input
                  autoFocus
                  className="w-full bg-white text-xs font-normal text-black outline-none px-1 rounded border border-blue-300"
                  value={editingFileName}
                  onChange={(e) => setEditingFileName(e.target.value)}
                  onKeyDown={(e) => {
                    // Enter/Escape both close the input, which fires onBlur;
                    // mark it so blur neither double-submits nor commits a cancel.
                    if (e.key === 'Enter') { e.currentTarget.dataset.settled = '1'; onFileRename(file._id); }
                    if (e.key === 'Escape') { e.currentTarget.dataset.settled = '1'; setEditingFileId(null); }
                  }}
                  onClick={(e) => e.stopPropagation()}
                  onBlur={(e) => { if (!e.currentTarget.dataset.settled) onFileRename(file._id); }}
                />
              ) : (
                <span className="truncate flex-1" title={file.originalName}>{file.originalName}</span>
              )}
            </div>

            {/* Hover Actions */}
            {editingFileId !== file._id && (
              <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-1 bg-white/50 backdrop-blur-sm rounded-sm">
                <button
                  onClick={(e) => { e.stopPropagation(); setEditingFileName(file.originalName); setEditingFileId(file._id); }}
                  className="p-1 hover:text-blue-600 rounded"
                >
                  <Edit2 className="w-3 h-3" />
                </button>
                <button
                  onClick={(e) => onFileDelete(file._id, e)}
                  className="p-1 hover:text-red-600 rounded"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>
        ))}

        <Button
          variant="secondary"
          size="sm"
          className="mt-2 text-xs border-dashed w-full shadow-none"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : <><Plus className="w-3 h-3 mr-1" />Add File</>}
        </Button>
        <input type="file" ref={fileInputRef} onChange={onFileUpload} className="hidden" accept=".txt,.md,.doc,.docx,.tex" />
      </div>
    </div>
  );
}
