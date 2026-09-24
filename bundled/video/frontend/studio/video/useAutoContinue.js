import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, patchJson, postJson } from '@lds/plugin-sdk';
import { autoContinueUrl, autoStateKey } from './videoAutoContinue';

export default function useAutoContinue(onChange) {
  const [session, setSession] = useState(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const revision = useRef(0);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const lastKey = useRef('');
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const accept = useCallback((reply) => {
    const next = reply.session || null;
    setSession(next);
    setReady(true);
    const key = autoStateKey(next);
    if (key !== lastKey.current) {
      lastKey.current = key;
      onChangeRef.current?.();
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    let timer;
    const controller = new AbortController();
    const poll = async () => {
      const version = revision.current;
      try {
        const reply = await apiFetch(autoContinueUrl(), { signal: controller.signal, background: true });
        if (!stopped && version === revision.current && !inFlight.current) {
          accept(reply);
          setPollError('');
        }
      } catch (err) {
        if (!stopped && version === revision.current && !inFlight.current) {
          setReady(false);
          setPollError(err?.message || 'Cannot read Auto status. Reconnecting…');
        }
      } finally {
        if (!stopped) timer = setTimeout(poll, 2500);
      }
    };
    poll();
    return () => {
      stopped = true;
      mounted.current = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [accept]);

  const act = useCallback(async (action, body) => {
    if (inFlight.current) return false;
    inFlight.current = true;
    revision.current += 1;
    setBusy(true);
    setError('');
    try {
      const reply = action === 'update'
        ? await patchJson(autoContinueUrl(), body)
        : await postJson(autoContinueUrl(action === 'start' ? '' : action), body);
      if (mounted.current) accept(reply);
      return true;
    } catch (err) {
      if (mounted.current) setError(err?.message || 'The Auto request failed. Check its status before retrying.');
      return false;
    } finally {
      revision.current += 1;
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }, [accept]);

  return { session, ready, busy, error: error || pollError, act };
}
