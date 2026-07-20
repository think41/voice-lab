import type { AgentConfig, Provider } from '../lib/types';

type Option = { value: string; label: string };

// Must stay in sync with SUPPORTED_MODELS_BY_PROVIDER in server/app/schemas/agent.py.
// Bare IDs are Gemini (native ADK); "provider/model" IDs run via ADK's LiteLLM wrapper
// and need the matching OPENAI_API_KEY / ANTHROPIC_API_KEY in server/.env.
export const modelOptions: Option[] = [
  { value: 'gemini-3.5-flash', label: 'Gemini 3.5 Flash' },
  { value: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash Lite' },
  { value: 'openai/gpt-5.1', label: 'GPT-5.1 (OpenAI)' },
  { value: 'openai/gpt-5-mini', label: 'GPT-5 Mini (OpenAI)' },
  { value: 'anthropic/claude-sonnet-5', label: 'Claude Sonnet 5 (Anthropic)' },
  { value: 'anthropic/claude-haiku-4-5', label: 'Claude Haiku 4.5 (Anthropic)' },
  { value: 'anthropic/claude-opus-4-8', label: 'Claude Opus 4.8 (Anthropic)' },
  { value: 'xai/grok-4', label: 'Grok 4 (xAI)' },
  { value: 'xai/grok-3-mini', label: 'Grok 3 Mini (xAI)' },
  { value: 'groq/llama-3.3-70b-versatile', label: 'Llama 3.3 70B (Groq)' },
  { value: 'groq/llama-3.1-8b-instant', label: 'Llama 3.1 8B Instant (Groq)' },
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

// Providers selectable for STT/TTS in the builder. 'sarvam' is in the Provider
// union only for the TTS cost-comparison view and has no builder catalog.
type SpeechProvider = Extract<Provider, 'deepgram' | 'elevenlabs'>;

const sttModelOptionsByProvider: Record<SpeechProvider, Option[]> = {
  deepgram: [
    { value: 'nova-3', label: 'Nova-3' },
  ],
  elevenlabs: [
    { value: 'scribe_v2_realtime', label: 'Scribe v2 Realtime' },
  ],
};

const defaultSttModelByProvider: Record<SpeechProvider, string> = {
  deepgram: 'nova-3',
  elevenlabs: 'scribe_v2_realtime',
};

const defaultTtsVoiceByProvider: Record<SpeechProvider, string> = {
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

function normalizeProvider(provider: string): SpeechProvider {
  return provider === 'elevenlabs' ? 'elevenlabs' : 'deepgram';
}
