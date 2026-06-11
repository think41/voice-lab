def test_pipecat_adk_core_imports() -> None:
    from pipecat_adk import AdkInterruptionPlugin, AdkLLMService, SessionParams, VqlTTSMixin

    assert AdkInterruptionPlugin is not None
    assert AdkLLMService is not None
    assert SessionParams is not None
    assert VqlTTSMixin is not None


def test_pipecat_deepgram_services_import() -> None:
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.deepgram.tts import DeepgramTTSService

    assert DeepgramSTTService is not None
    assert DeepgramTTSService is not None
