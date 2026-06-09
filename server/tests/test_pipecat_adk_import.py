def test_pipecat_adk_core_imports() -> None:
    from pipecat_adk import AdkInterruptionPlugin, AdkLLMService, SessionParams, VqlTTSMixin

    assert AdkInterruptionPlugin is not None
    assert AdkLLMService is not None
    assert SessionParams is not None
    assert VqlTTSMixin is not None
