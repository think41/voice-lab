// LLM model options are static (Gemini variants; app is tied to ADK+Gemini today).
export const modelOptions = [
  { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
  { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' }
];

// Provider is Deepgram-only for now; kept as a static single-item list.
export const sttProviderOptions = [{ value: 'deepgram', label: 'Deepgram' }];
export const ttsProviderOptions = [{ value: 'deepgram', label: 'Deepgram' }];

// Fallbacks used when /api/providers/deepgram/catalog fails or hasn't loaded.
export const fallbackSttOptions = [
  { value: 'nova-3-general', label: 'Nova-3 General' },
  { value: 'nova-2-general', label: 'Nova-2 General' },
  { value: 'nova-2-conversationalai', label: 'Nova-2 Conversational AI' },
  { value: 'nova-2-phonecall', label: 'Nova-2 Phonecall' }
];

export const fallbackVoiceOptions = [
  { value: 'aura-asteria-en', label: 'Aura Asteria' },
  { value: 'aura-luna-en', label: 'Aura Luna' },
  { value: 'aura-stella-en', label: 'Aura Stella' },
  { value: 'aura-athena-en', label: 'Aura Athena' },
  { value: 'aura-2-thalia-en', label: 'Aura 2 Thalia' },
  { value: 'aura-2-orion-en', label: 'Aura 2 Orion' },
  { value: 'aura-2-vesta-en', label: 'Aura 2 Vesta' },
  { value: 'aura-2-zeus-en', label: 'Aura 2 Zeus' }
];
