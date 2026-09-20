// ProcessStep must survive React StrictMode's dev-only mount → unmount → mount:
// the unmount aborts the first stream, so the remount has to start a new one.
// Before the fix a ref guard skipped the restart and the page sat at 0% forever.
import { StrictMode } from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProcessStep } from './ProcessStep';
import useDeepScanStore from '../../store/useDeepScanStore';

const EVENTS = [
  { stage: 1, log: 'Step 1/6 — Ingesting document...' },
  { stage: 1, log: '✅ Static formatting complete — Score: 99%', compliance_score: 99 },
  { is_final: true, latex: '\\documentclass{article}' },
];

function sseResponse() {
  const body = EVENTS.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
  return new Response(body, { headers: { 'content-type': 'text/event-stream' } });
}

// Behaves like the browser's fetch: rejects with AbortError once aborted, and
// answers on a later tick so an immediate abort lands first.
function fakeFetch(url, { signal } = {}) {
  return new Promise((resolve, reject) => {
    const abort = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
    if (signal?.aborted) return abort();
    signal?.addEventListener('abort', abort);
    setTimeout(() => resolve(sseResponse()), 0);
  });
}

describe('ProcessStep', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(fakeFetch));
    useDeepScanStore.setState({
      uploadedFile: new File(['x'], 'paper.docx'),
      targetStyle: 'ieee',
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('streams server events under StrictMode', async () => {
    render(<StrictMode><ProcessStep /></StrictMode>);

    expect(await screen.findByText(/Static formatting complete/)).toBeInTheDocument();
    expect(await screen.findByText('Pipeline Complete')).toBeInTheDocument();
  });
});
