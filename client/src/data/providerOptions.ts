import type { AgentConfig, Provider } from '../lib/types';

type Option = { value: string; label: string };

export const modelOptions: Option[] = [
  { value: 'gemini-3.5-flash', label: 'Gemini 3.5 Flash' },
  { value: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash Lite' },
];

export const sttProviderOptions: Option[] = [
  { value: 'deepgram', label: 'Deepgram' },
  { value: 'elevenlabs', label: 'ElevenLabs' },
];

export const ttsProviderOptions: Option[] = [
  { value: 'deepgram', label: 'Deepgram' },
  { value: 'elevenlabs', label: 'ElevenLabs' },
];

export const deepgramVoiceOptions: Option[] = [
  { value: 'aura-asteria-en', label: 'Aura Asteria' },
  { value: 'aura-luna-en', label: 'Aura Luna' },
  { value: 'aura-stella-en', label: 'Aura Stella' },
  { value: 'aura-athena-en', label: 'Aura Athena' },
  { value: 'aura-2-thalia-en', label: 'Aura 2 Thalia' },
  { value: 'aura-2-orion-en', label: 'Aura 2 Orion' },
  { value: 'aura-2-vesta-en', label: 'Aura 2 Vesta' },
  { value: 'aura-2-zeus-en', label: 'Aura 2 Zeus' },
];

export const elevenLabsVoiceOptions: Option[] = [
  { value: 'JBFqnCBsd6RMkjVDRZzb', label: 'George' },
  { value: '21m00Tcm4TlvDq8ikWAM', label: 'Rachel' },
  { value: 'AZnzlk1XvdvUeBnXmlld', label: 'Domi' },
  { value: 'EXAVITQu4vr4xnSDxMaL', label: 'Bella' },
  { value: 'ErXwobaYiN019PkySvjV', label: 'Antoni' },
  { value: 'MF3mGyEYCl7XYWbV9V6O', label: 'Elli' },
  { value: 'TxGEqnHWrfWFTfGW9XjX', label: 'Josh' },
  { value: 'VR6AewLTigWG4xSOukaG', label: 'Arnold' },
  { value: 'pNInz6obpgDQGcFmaJgB', label: 'Adam' },
  { value: 'yoZ06aMxZJJ28mfd3POQ', label: 'Sam' },
];

const sttModelOptionsByProvider: Record<Provider, Option[]> = {
  deepgram: [
    { value: 'nova-3', label: 'Nova-3' },
  ],
  elevenlabs: [
    { value: 'scribe_v2_realtime', label: 'Scribe v2 Realtime' },
  ],
};

const defaultSttModelByProvider: Record<Provider, string> = {
  deepgram: 'nova-3',
  elevenlabs: 'scribe_v2_realtime',
};

const defaultTtsVoiceByProvider: Record<Provider, string> = {
  deepgram: 'aura-asteria-en',
  elevenlabs: 'JBFqnCBsd6RMkjVDRZzb',
};

const supportedDeepgramVoices = new Set(deepgramVoiceOptions.map((option) => option.value));
const supportedElevenLabsVoices = new Set(elevenLabsVoiceOptions.map((option) => option.value));

export function getSttModelOptions(provider: string): Option[] {
  return sttModelOptionsByProvider[normalizeProvider(provider)] ?? sttModelOptionsByProvider.deepgram;
}

export function getDefaultSttModel(provider: string): string {
  return defaultSttModelByProvider[normalizeProvider(provider)];
}

export function getDefaultTtsVoice(provider: string): string {
  return defaultTtsVoiceByProvider[normalizeProvider(provider)];
}

export function getTtsVoiceOptions(provider: string): Option[] {
  return normalizeProvider(provider) === 'elevenlabs' ? elevenLabsVoiceOptions : deepgramVoiceOptions;
}

export function usesTtsVoiceSelect(provider: string): boolean {
  return true;
}

export function getTtsVoiceFieldLabel(provider: string): string {
  return 'Voice';
}

export function getTtsVoicePlaceholder(provider: string): string {
  return '';
}

export function normalizeSpeechConfig(config: AgentConfig): AgentConfig {
  const sttProvider = normalizeProvider(config.stt_provider);
  const ttsProvider = normalizeProvider(config.tts_provider);
  const normalizedSttModel =
    sttProvider === 'deepgram' &&
    (config.stt_model === 'nova-3-monolingual' || config.stt_model === 'nova-3-multilingual')
      ? 'nova-3'
      : config.stt_model;
  const sttModelOptions = getSttModelOptions(sttProvider).map((option) => option.value);
  const sttModel = sttModelOptions.includes(normalizedSttModel)
    ? normalizedSttModel
    : getDefaultSttModel(sttProvider);

  let ttsVoice = config.tts_voice;
  if (ttsProvider === 'deepgram') {
    ttsVoice = ttsVoice === 'Rachel' ? 'aura-asteria-en' : ttsVoice;
    if (!supportedDeepgramVoices.has(ttsVoice)) {
      ttsVoice = getDefaultTtsVoice('deepgram');
    }
  } else if (!supportedElevenLabsVoices.has(ttsVoice)) {
    ttsVoice = getDefaultTtsVoice('elevenlabs');
  }

  return {
    ...config,
    stt_provider: sttProvider,
    stt_model: sttModel,
    tts_provider: ttsProvider,
    tts_voice: ttsVoice,
  };
}

function normalizeProvider(provider: string): Provider {
  return provider === 'elevenlabs' ? 'elevenlabs' : 'deepgram';
}
