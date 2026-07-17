from pydantic import BaseModel


class TestSessionCreate(BaseModel):
    agent_id: str
    user_id: str = "local-user"
    evaluate_mode: bool = False


class TestSessionRead(BaseModel):
    run_id: str
    adk_session_id: str
    websocket_url: str
    first_message: str | None = None


class TextTurnCreate(BaseModel):
    message: str
    user_id: str = "local-user"


class TextTurnRead(BaseModel):
    run_id: str
    user_text: str
    assistant_text: str
