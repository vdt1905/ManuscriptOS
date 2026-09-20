// useSSE — POST-and-stream Server-Sent Events with proper cleanup (Track A3).
//
// Extracts the getReader()/TextDecoder/split('\n\n') loop that used to live
// inline in DeepScan.jsx. The two real bugs it fixes:
//   1. NO AbortController before — navigating away mid-stream left the fetch
//      running and called setState on an unmounted component (leak + warning).
//      This hook aborts on unmount and on an explicit stop().
//   2. The frame parser is now a PURE function (parseSSEChunk) so the tricky
//      partial-chunk buffering is unit-tested without a DOM.
//
// The hook is generic: it hands each parsed JSON event to an onEvent callback.
// All business logic (what to do with each event) stays in the caller.
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Parse a rolling SSE buffer into complete events + the leftover partial frame.
 * SSE frames are separated by a blank line ("\n\n"); each data line is
 * "data: <json>". A frame may arrive split across network chunks, so the
 * trailing incomplete frame is returned as `rest` to prepend to the next chunk.
 *
 * @param {string} buffer  accumulated text (previous rest + new chunk)
 * @returns {{ events: any[], rest: string }}  parsed JSON events + leftover
 */
export function parseSSEChunk(buffer) {
  const frames = buffer.split('\n\n');
  const rest = frames.pop() ?? ''; // last item is the (possibly partial) next frame
  const events = [];
  for (const frame of frames) {
    const trimmed = frame.trim();
    if (!trimmed || !trimmed.startsWith('data:')) continue;
    const json = trimmed.slice(trimmed.indexOf('data:') + 5).trim();
    try {
      events.push(JSON.parse(json));
    } catch {
      // Ignore unparseable frames (keep-alives, comments) — never throw here.
    }
  }
  return { events, rest };
}

/**
 * @typedef {Object} UseSSEOptions
 * @property {(event:any)=>void} onEvent   called for each parsed JSON event
 * @property {()=>void}          [onDone]  called when the stream ends cleanly
 * @property {(err:{message:string})=>void} [onError]  connection/stream error
 * @property {number} [idleTimeoutMs]  abort and report an error if nothing at
 *   all (not even a heartbeat) arrives for this long. Off when unset.
 */

/**
 * @param {UseSSEOptions} options
 * @returns {{ start:(url:string,init?:RequestInit)=>Promise<void>, stop:()=>void, status:'idle'|'streaming'|'done'|'error' }}
 */
export function useSSE({ onEvent, onDone, onError, idleTimeoutMs } = {}) {
  const [status, setStatus] = useState('idle');
  const controllerRef = useRef(null);
  // Keep callbacks in refs so start() doesn't need them as deps (stable identity).
  const cbs = useRef({ onEvent, onDone, onError, idleTimeoutMs });
  cbs.current = { onEvent, onDone, onError, idleTimeoutMs };

  const stop = useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
  }, []);

  const start = useCallback(async (url, init = {}) => {
    stop(); // cancel any in-flight stream first
    const controller = new AbortController();
    controllerRef.current = controller;
    setStatus('streaming');

    // Watchdog: a live server sends events or heartbeats, so a long silence
    // means the connection is gone. Re-armed on every chunk received.
    const idleMs = cbs.current.idleTimeoutMs;
    let idleTimer = null;
    let timedOut = false;
    const armIdleTimer = () => {
      if (!idleMs) return;
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => { timedOut = true; controller.abort(); }, idleMs);
    };
    armIdleTimer();

    try {
      const res = await fetch(url, { ...init, signal: controller.signal });
      if (!res.ok || !res.body) {
        throw new Error(`Stream failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let done = false;

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        armIdleTimer();
        done = readerDone;
        if (value) buffer += decoder.decode(value, { stream: true });

        const { events, rest } = parseSSEChunk(buffer);
        buffer = rest;
        for (const event of events) {
          cbs.current.onEvent?.(event);
        }
      }
      // Flush any final complete frame left in the buffer.
      const { events } = parseSSEChunk(buffer + '\n\n');
      for (const event of events) cbs.current.onEvent?.(event);

      setStatus('done');
      cbs.current.onDone?.();
    } catch (err) {
      if (err?.name === 'AbortError' && !timedOut) return; // intentional stop/unmount — silent
      setStatus('error');
      const message = timedOut
        ? `No response from the server for ${Math.round(idleMs / 1000)}s. The connection seems to have dropped.`
        : err?.message || 'Connection error';
      cbs.current.onError?.({ message });
    } finally {
      clearTimeout(idleTimer);
      // Only clear the ref if it still points at this stream (a newer start()
      // may have replaced it).
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }, [stop]);

  // Abort on unmount — the core leak fix.
  useEffect(() => stop, [stop]);

  return { start, stop, status };
}

export default useSSE;
