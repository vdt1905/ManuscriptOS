/**
 * Deep Scan Tool — Standalone 5-Step Pipeline Wizard
 * ====================================================
 * Upload → Configure → Process → LaTeX → Agent
 *
 * This is a thin shell (Track A5 decomposition). Each step lives in its own file
 * under ./deep-scan/, and shared nav/constants are in ./deep-scan/StepNav +
 * constants. State is the isolated useDeepScanStore.
 */
import { useEffect } from 'react';
import useDeepScanStore from '../store/useDeepScanStore';
import useAppStore from '../store/useAppStore';
import { projectService } from '../services';
import { PageMeta } from '../components/PageMeta';
import { SidebarNav } from './deep-scan/StepNav';
import { UploadStep } from './deep-scan/UploadStep';
import { ConfigureStep } from './deep-scan/ConfigureStep';
import { ProcessStep } from './deep-scan/ProcessStep';
import { LaTeXStep } from './deep-scan/LaTeXStep';
import { AgentStep } from './deep-scan/AgentStep';

export function DeepScan() {
  const currentStep = useDeepScanStore((s) => s.currentStep);
  const setStep = useDeepScanStore((s) => s.setStep);
  const isProcessingDone = useDeepScanStore((s) => s.isProcessingDone);
  const resetPipeline = useDeepScanStore((s) => s.resetPipeline);
  const setUploadedFile = useDeepScanStore((s) => s.setUploadedFile);

  const deepScanProjectId = useAppStore((s) => s.deepScanProjectId);
  const deepScanSourceFileName = useAppStore((s) => s.deepScanSourceFileName);
  const setDeepScanProjectId = useAppStore((s) => s.setDeepScanProjectId);

  // "Format (Deep Scan)" in a project workspace lands here with the project
  // id set. Projects keep a file's extracted text (not the original binary),
  // so seed the wizard with that text and jump straight to Configure; before
  // this the button just opened an empty upload step.
  useEffect(() => {
    if (!deepScanProjectId) return;
    let cancelled = false;
    (async () => {
      try {
        const project = await projectService.get(deepScanProjectId);
        const files = project?.files || [];
        const file = files.find((f) => (f.originalName || '').replace(/\.[^.]+$/, '') === deepScanSourceFileName) || files[0];
        if (!file || cancelled) return;
        const text = (file.content || '').replace(/<\/(p|div|h\d|li|br)>/gi, '\n').replace(/<[^>]+>/g, '');
        resetPipeline();
        setUploadedFile(new File([text], `${deepScanSourceFileName || 'document'}.txt`, { type: 'text/plain' }));
        setStep(2);
      } finally {
        if (!cancelled) setDeepScanProjectId(null);
      }
    })();
    return () => { cancelled = true; };
  }, [deepScanProjectId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex h-[calc(100vh-80px)] rounded-2xl overflow-hidden border border-[var(--color-surface-200)] shadow-lg bg-[var(--color-surface-50)]">
      <PageMeta title="Deep Scan" description="AI pipeline that reformats your manuscript to a target journal style and compiles it to PDF." />
      <SidebarNav currentStep={currentStep} onStepClick={setStep} disabled={currentStep === 3 && !isProcessingDone} />
      <div className="flex-1 flex flex-col overflow-hidden bg-[var(--color-surface-50)]">
        <div className="flex-1 overflow-y-auto p-8 scroll-smooth hide-scrollbar">
          {currentStep === 1 && <UploadStep />}
          {currentStep === 2 && <ConfigureStep />}
          {currentStep === 3 && <ProcessStep />}
          {currentStep === 4 && <LaTeXStep />}
          {currentStep === 5 && <AgentStep />}
        </div>
      </div>
    </div>
  );
}

export default DeepScan;
