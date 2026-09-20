// LaTeX split workspace — outline + Monaco + PDF preview (presentational).
import { ListOrdered, FileDown } from 'lucide-react';
import MonacoEditor from '@monaco-editor/react';

export function LatexEditorPane({
  activeFile, localContent, onEditorChange,
  latexOutline, latexEditorRef, latexPreviewRef,
  latexCompiling, latexCompiled,
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-1 min-h-0">
        {/* Outline Sidebar */}
        <div className="hidden md:flex flex-col w-52 bg-[#1e1e1e] border-r border-[#333] shrink-0 text-[#ccc] overflow-hidden">
          <div className="flex items-center px-3 py-2 border-b border-[#333] shrink-0">
            <ListOrdered className="h-3.5 w-3.5 mr-2" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">Outline</span>
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            {latexOutline.length === 0 ? (
              <div className="px-3 py-3 text-[10px] text-[#888] italic text-center">No sections. Use \section{'{...}'} to build an outline.</div>
            ) : latexOutline.map((item) => {
              const pl = item.level === 1 ? 'pl-3' : item.level === 2 ? 'pl-6' : 'pl-9';
              const sz = item.level === 1 ? 'text-[12px] font-medium text-white' : 'text-[11px] text-[#ccc]';
              return (
                <div key={item.id} className={`flex items-center py-1 cursor-pointer hover:bg-[#2a2d2e] ${pl}`}
                  onClick={() => { if (latexEditorRef.current) { latexEditorRef.current.revealLineInCenter(item.line); latexEditorRef.current.setPosition({ lineNumber: item.line, column: 1 }); latexEditorRef.current.focus(); } }}
                >
                  <span className={`${sz} truncate pr-2`} title={item.title}>{item.title}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Monaco Editor */}
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-[var(--color-surface-200)] bg-[var(--color-surface-50)] shrink-0 text-xs">
            <span className="font-semibold text-[var(--color-text-main)]">{activeFile.originalName}</span>
          </div>
          <div className="flex-1">
            <MonacoEditor
              height="100%"
              defaultLanguage="latex"
              value={localContent}
              onChange={onEditorChange}
              theme="vs-light"
              onMount={(editor) => { latexEditorRef.current = editor; }}
              options={{ minimap: { enabled: false }, fontSize: 14, wordWrap: 'on', lineNumbers: 'on', padding: { top: 12 }, scrollBeyondLastLine: false, smoothScrolling: true }}
            />
          </div>
        </div>

        {/* PDF Preview */}
        <div className="flex flex-col flex-1 overflow-hidden border-l border-[var(--color-surface-300)]">
          <div className="flex items-center px-3 py-1.5 border-b border-[var(--color-surface-200)] bg-[var(--color-surface-50)] shrink-0 text-xs">
            <FileDown className="h-3.5 w-3.5 mr-2 text-[var(--color-text-muted)]" />
            <span className="font-semibold text-[var(--color-text-main)]">PDF Preview</span>
          </div>
          <div className="flex-1 bg-[#525659] relative">
            <iframe ref={latexPreviewRef} name="latex-pdf-preview-ws" className={`w-full h-full border-none transition-opacity duration-300 ${latexCompiling ? 'opacity-50' : 'opacity-100'}`} title="Compiled PDF" />
            {!latexCompiled && !latexCompiling && (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-white/70">
                <FileDown className="h-12 w-12 mb-3 opacity-50" />
                <p className="text-base font-medium">No PDF Generated</p>
                <p className="text-xs mt-1">Write LaTeX and click Compile PDF</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
