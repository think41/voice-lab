import type { AgentConfig } from '../lib/types';

export const defaultAgentConfig: AgentConfig = {
  name: 'Hotel Booking',
  model: 'gemini-2.0-flash',
  instruction: 'You are a concise hotel booking voice assistant. Ask for dates, room type, guest count, and confirm before booking.',
  stt_provider: 'deepgram',
  stt_model: 'nova-2',
  tts_provider: 'deepgram',
  tts_voice: 'aura-asteria-en',
  temperature: 0.4,
  first_message: 'Hi, this is VoiceLab. How can I help with your hotel booking?',
  tools: [
    { name: 'check_availability', description: 'Check room availability for requested dates.', enabled: true },
    { name: 'create_booking', description: 'Create a reservation after confirmation.', enabled: true },
    { name: 'end_call', description: 'Politely end the test call.', enabled: true }
  ],
  metadata: {}
};
