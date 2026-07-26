import uuid

import pytest

from database.enums import ChatStatus, ChatTurnEventType, MessageRole
from database.repositories import (
    ChatEvidenceRepo,
    ChatMessageRepo,
    ChatSessionRepo,
    ChatTurnEventRepo,
)
from database.schemas import ChatSessionCreate
from database.session import get_session


@pytest.mark.asyncio
async def test_chat_session_message_evidence_and_events():
    external_id = f"CH-{uuid.uuid4().hex[:8].upper()}"

    async with get_session() as session:
        session_repo = ChatSessionRepo(session)
        message_repo = ChatMessageRepo(session)
        evidence_repo = ChatEvidenceRepo(session)
        event_repo = ChatTurnEventRepo(session)

        chat_session = await session_repo.create(
            ChatSessionCreate(external_id=external_id, chat_name="Test Chat")
        )
        assert chat_session.status == ChatStatus.IDLE

        user_msg = await message_repo.append_user(chat_session.id, "What is heap sort?")
        assistant_msg = await message_repo.append_assistant(chat_session.id, "Heap sort is ...")

        evidences = await evidence_repo.replace_for_turn(
            chat_session.id,
            assistant_msg.id,
            [
                {
                    "content": "Heap sort algorithm description",
                    "score": 0.91,
                    "rerank_score": 0.91,
                    "metadata": {"asset_name": "algo.pdf", "modality": "pdf"},
                }
            ],
        )
        assert len(evidences) == 1
        assert evidences[0].rank == 0

        event = await event_repo.append(
            chat_session.id,
            ChatTurnEventType.STEP_START,
            turn_seq=1,
            message_id=assistant_msg.id,
            step_name="research_search",
            to_status=ChatStatus.RESEARCHING,
            detail={"keywords": ["heap"]},
        )
        assert event.step_name == "research_search"

        await session_repo.update_status(chat_session.id, ChatStatus.IDLE)
        messages = await message_repo.list_by_session(chat_session.id)
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[1].role == MessageRole.ASSISTANT

        events = await event_repo.list_recent(chat_session.id, limit=5)
        assert events
        assert events[0].event_type == ChatTurnEventType.STEP_START

        await session_repo.delete(chat_session.id)
