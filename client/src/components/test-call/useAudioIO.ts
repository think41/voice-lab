import { useCallback, useEffect, useRef } from 'react';

interface AudioIOOptions {
  /** Called for each captured mic chunk (16-bit PCM buffer). */
  onCapture: (chunk: ArrayBuffer) => void;
  /** Called once when the browser has consented to mic capture and streaming begins. */
  onCaptureStarted?: () => void;
  /** Called on non-fatal audio errors that the UI should surface. */
  onError?: (message: string) => void;
}

/**
 * Owns all voice-side audio state: mic capture, PCM playback scheduling,
 * teardown, and the "resume mic after agent finishes speaking" coordination.
 *
 * The TestCallPanel wires this to the WebSocket via `onCapture` (mic → socket)
 * and by calling `enqueuePlayback` / `signalServerStopped` from `socket.onmessage`.
 */
export function useAudioIO({ onCapture, onCaptureStarted, onError }: AudioIOOptions) {
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const gainRef = useRef<GainNode | null>(null);
  const microphoneStartedRef = useRef(false);
  const captureFallbackRef = useRef<number | null>(null);
  const playbackEndFallbackRef = useRef<number | null>(null);
  const playbackRef = useRef({
    activeSources: 0,
    serverStopped: false,
    started: false,
    nextTime: 0,
  });

  const onCaptureRef = useRef(onCapture);
  const onCaptureStartedRef = useRef(onCaptureStarted);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onCaptureRef.current = onCapture;
    onCaptureStartedRef.current = onCaptureStarted;
    onErrorRef.current = onError;
  });

  const clearFallbacks = useCallback(() => {
    if (captureFallbackRef.current !== null) {
      window.clearTimeout(captureFallbackRef.current);
      captureFallbackRef.current = null;
    }
    if (playbackEndFallbackRef.current !== null) {
      window.clearTimeout(playbackEndFallbackRef.current);
      playbackEndFallbackRef.current = null;
    }
  }, []);

  const resetPlaybackState = useCallback(() => {
    playbackRef.current = { activeSources: 0, serverStopped: false, started: false, nextTime: 0 };
  }, []);

  const beginCaptureNow = useCallback(() => {
    const context = audioContextRef.current;
    const stream = mediaStreamRef.current;
    if (!context || !stream || microphoneStartedRef.current) return;
    clearFallbacks();
    microphoneStartedRef.current = true;

    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const gain = context.createGain();
    gain.gain.value = 0;

    processor.onaudioprocess = (event) => {
      const samples = event.inputBuffer.getChannelData(0);
      const pcm = float32ToPcm16(samples);
      onCaptureRef.current(pcm.buffer as ArrayBuffer);
    };

    source.connect(processor);
    processor.connect(gain);
    gain.connect(context.destination);
    sourceRef.current = source;
    processorRef.current = processor;
    gainRef.current = gain;
    onCaptureStartedRef.current?.();
  }, [clearFallbacks]);

  const maybeBeginCaptureAfterPlayback = useCallback(() => {
    const state = playbackRef.current;
    if (!state.serverStopped || state.activeSources > 0) return;
    clearFallbacks();
    playbackEndFallbackRef.current = window.setTimeout(beginCaptureNow, 250);
  }, [beginCaptureNow, clearFallbacks]);

  /** Ask the browser for mic access and build the capture graph (deferred until scheduleCapture). */
  const acquireMic = useCallback(async (): Promise<AudioContext> => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const context = new AudioContext();
    mediaStreamRef.current = stream;
    audioContextRef.current = context;
    return context;
  }, []);

  /**
   * Schedule mic capture to begin.
   * If `waitForServerAudio` is true, we wait for either `signalServerStopped()`
   * or a 15s fallback (in case the server never speaks first).
   */
  const scheduleCapture = useCallback((waitForServerAudio: boolean) => {
    if (waitForServerAudio) {
      captureFallbackRef.current = window.setTimeout(beginCaptureNow, 15000);
    } else {
      beginCaptureNow();
    }
  }, [beginCaptureNow]);

  const enqueuePlayback = useCallback(async (chunk: ArrayBuffer) => {
    if (chunk.byteLength === 0) return;
    const context = playbackContextRef.current ?? createPlaybackContext();
    playbackContextRef.current = context;
    if (context.state === 'suspended') {
      try { await context.resume(); } catch { /* ignore */ }
    }

    const samples = new Int16Array(chunk);
    const buffer = context.createBuffer(1, samples.length, 24000);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i += 1) channel[i] = samples[i] / 32768;

    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    const state = playbackRef.current;
    const startAt = Math.max(context.currentTime + 0.02, state.nextTime);
    state.activeSources += 1;
    state.started = true;
    source.onended = () => {
      const s = playbackRef.current;
      s.activeSources = Math.max(0, s.activeSources - 1);
      maybeBeginCaptureAfterPlayback();
    };
    try {
      source.start(startAt);
    } catch {
      state.activeSources = Math.max(0, state.activeSources - 1);
      onErrorRef.current?.('Audio arrived, but browser playback failed.');
      return;
    }
    state.nextTime = startAt + buffer.duration;
  }, [maybeBeginCaptureAfterPlayback]);

  const signalServerStopped = useCallback(() => {
    playbackRef.current.serverStopped = true;
    maybeBeginCaptureAfterPlayback();
  }, [maybeBeginCaptureAfterPlayback]);

  /** Force mic capture to begin now (used on runtime error to unblock the user). */
  const forceCaptureStart = useCallback(() => beginCaptureNow(), [beginCaptureNow]);

  const cleanup = useCallback(async () => {
    clearFallbacks();
    microphoneStartedRef.current = false;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    gainRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current = null;
    gainRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      await audioContextRef.current.close();
    }
    audioContextRef.current = null;
    if (playbackContextRef.current && playbackContextRef.current.state !== 'closed') {
      await playbackContextRef.current.close();
    }
    playbackContextRef.current = null;
    resetPlaybackState();
  }, [clearFallbacks, resetPlaybackState]);

  useEffect(() => () => { void cleanup(); }, [cleanup]);

  return { acquireMic, scheduleCapture, enqueuePlayback, signalServerStopped, forceCaptureStart, cleanup };
}

function createPlaybackContext(): AudioContext {
  // Server sends 24kHz linear16 PCM. Request matching rate; fall back to default
  // on devices that reject specific rates (buffer's own rate drives resampling).
  try {
    return new AudioContext({ sampleRate: 24000 });
  } catch {
    return new AudioContext();
  }
}

function float32ToPcm16(samples: Float32Array): Int16Array {
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return pcm;
}
