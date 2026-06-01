import json
import os
import time
import uuid
from datetime import datetime

from prompts import REWRITE_REQUEST_PROMPT
from src.telemetry.logger import logger
from test import (
    collect_research_for_destinations,
    create_llm_provider,
    destination_agent,
    intent_agent,
    load_environment,
    normalize_trip_params,
    planning_agent,
)
from src.tools.travel_api_tools import validate_travel_input


HISTORY_PATH = "history.json"
MAX_HISTORY_MESSAGES = 8
MAX_INPUT_LENGTH = 2000

# Simple state for collecting trip information across conversation
_current_trip_request = {}


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_conversation(title: str = "Hội thoại mới") -> dict:
    now = _timestamp()
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def _normalize_history_store(data) -> dict:
    if isinstance(data, list):
        conversation = _new_conversation("Hội thoại đã lưu")
        conversation["messages"] = data
        return {
            "active_conversation_id": conversation["id"],
            "conversations": [conversation],
        }

    if not isinstance(data, dict):
        conversation = _new_conversation()
        return {
            "active_conversation_id": conversation["id"],
            "conversations": [conversation],
        }

    conversations = data.get("conversations")
    if not isinstance(conversations, list) or not conversations:
        conversation = _new_conversation()
        conversations = [conversation]

    normalized = []
    for index, conversation in enumerate(conversations, start=1):
        if not isinstance(conversation, dict):
            continue
        conversation_id = conversation.get("id") or str(uuid.uuid4())
        messages = conversation.get("messages")
        normalized.append(
            {
                "id": conversation_id,
                "title": conversation.get("title") or f"Hội thoại {index}",
                "created_at": conversation.get("created_at") or _timestamp(),
                "updated_at": conversation.get("updated_at") or _timestamp(),
                "messages": messages if isinstance(messages, list) else [],
            }
        )

    if not normalized:
        normalized = [_new_conversation()]

    active_id = data.get("active_conversation_id")
    if active_id not in {item["id"] for item in normalized}:
        active_id = normalized[-1]["id"]

    return {
        "active_conversation_id": active_id,
        "conversations": normalized,
    }


def load_history_store(path: str = HISTORY_PATH) -> dict:
    if not os.path.exists(path):
        return _normalize_history_store(None)

    try:
        with open(path, "r", encoding="utf-8") as history_file:
            data = json.load(history_file)
    except (json.JSONDecodeError, OSError):
        data = None

    store = _normalize_history_store(data)
    save_history_store(store, path=path)
    return store


def save_history_store(store: dict, path: str = HISTORY_PATH) -> None:
    with open(path, "w", encoding="utf-8") as history_file:
        json.dump(store, history_file, ensure_ascii=False, indent=2)


def get_conversations(store: dict) -> list:
    return store.get("conversations", [])


def get_active_conversation(store: dict) -> dict:
    conversations = get_conversations(store)
    active_id = store.get("active_conversation_id")
    for conversation in conversations:
        if conversation.get("id") == active_id:
            return conversation
    if conversations:
        store["active_conversation_id"] = conversations[-1]["id"]
        return conversations[-1]

    conversation = _new_conversation()
    store["active_conversation_id"] = conversation["id"]
    store["conversations"] = [conversation]
    return conversation


def get_active_messages(store: dict) -> list:
    return get_active_conversation(store).setdefault("messages", [])


def create_conversation(store: dict, title: str = "Hội thoại mới") -> dict:
    conversation = _new_conversation(title)
    store.setdefault("conversations", []).append(conversation)
    store["active_conversation_id"] = conversation["id"]
    return conversation


def set_active_conversation(store: dict, conversation_id: str) -> None:
    if conversation_id in {item.get("id") for item in get_conversations(store)}:
        store["active_conversation_id"] = conversation_id


def reset_history_store(path: str = HISTORY_PATH) -> dict:
    store = _normalize_history_store(None)
    save_history_store(store, path=path)
    return store


def append_message_to_active(
    store: dict,
    role: str,
    content: str,
    metadata: dict = None,
    path: str = HISTORY_PATH,
) -> None:
    item = {
        "timestamp": _timestamp(),
        "role": role,
        "content": content,
    }
    if metadata:
        item["metadata"] = metadata

    conversation = get_active_conversation(store)
    conversation.setdefault("messages", []).append(item)
    conversation["updated_at"] = item["timestamp"]
    if role == "user" and len(conversation["messages"]) == 1:
        conversation["title"] = content[:48] + ("..." if len(content) > 48 else "")
    save_history_store(store, path=path)


def load_history() -> list:
    return get_active_messages(load_history_store())


def save_history(history: list) -> None:
    conversation = _new_conversation("Hội thoại đã lưu")
    conversation["messages"] = history
    store = {
        "active_conversation_id": conversation["id"],
        "conversations": [conversation],
    }
    save_history_store(store)


def append_history(history: list, role: str, content: str, metadata: dict = None) -> None:
    item = {
        "timestamp": _timestamp(),
        "role": role,
        "content": content,
    }
    if metadata:
        item["metadata"] = metadata
    history.append(item)
    save_history(history)


def recent_dialogue(history: list) -> list:
    compact = []
    for message in history[-MAX_HISTORY_MESSAGES:]:
        compact.append(
            {
                "role": message.get("role"),
                "content": message.get("content"),
            }
        )
    return compact


def validate_user_input(user_input: str) -> str:
    """Sanitize and enforce guardrails on raw user input. Raises ValueError on violations."""
    stripped = user_input.strip()
    if not stripped:
        raise ValueError("Yêu cầu không được để trống.")
    if len(stripped) > MAX_INPUT_LENGTH:
        raise ValueError(
            f"Yêu cầu quá dài ({len(stripped)} ký tự). Tối đa {MAX_INPUT_LENGTH} ký tự."
        )
    return stripped


def rewrite_user_request(llm, history: list, user_input: str) -> str:
    if not history:
        return user_input

    prompt = json.dumps(
        {
            "recent_dialogue": recent_dialogue(history),
            "new_user_message": user_input,
        },
        ensure_ascii=False,
        indent=2,
    )
    response = llm.generate(prompt, system_prompt=REWRITE_REQUEST_PROMPT)
    rewritten = str(response.get("content", "")).strip()
    return rewritten or user_input


def run_planner_turn(llm, standalone_request: str) -> tuple:
    timings: dict = {}

    t0 = time.perf_counter()
    params = normalize_trip_params(intent_agent(llm, standalone_request))
    timings["intent_s"] = round(time.perf_counter() - t0, 2)

    if params.get("origin_missing"):
        answer = "Hãy cung cấp cho tôi thêm thông tin về địa điểm xuất phát của bạn"
        metadata = {
            "standalone_request": standalone_request,
            "params": params,
            "needs_origin": True,
            "timings": timings,
        }
        return answer, metadata
def run_planner_turn(llm, standalone_request: str, current_trip: dict = None) -> tuple:
    """Run a single turn of the travel planner with input validation."""

    # Merge with existing trip info
    trip = dict(current_trip) if current_trip else {}

    # Validate the request
    validation_result = validate_travel_input(standalone_request)

    # Update trip with validated info
    normalized = validation_result.get("normalized_input", {})
    if normalized.get("origin"):
        trip["origin"] = normalized["origin"]
    if normalized.get("destination"):
        trip["destination"] = normalized["destination"]
    if normalized.get("budget"):
        trip["budget"] = normalized["budget"]
    if normalized.get("people"):
        trip["people"] = normalized["people"]
    if normalized.get("days"):
        trip["days"] = normalized["days"]

    # If validation fails, ask follow-up
    if not validation_result["is_valid"]:
        follow_up = validation_result.get("follow_up_question", "Bạn cần cung cấp thêm thông tin.")
        assumptions = validation_result.get("assumptions", [])
        answer = follow_up
        if assumptions:
            answer += "\n\n" + "Giả định: " + "; ".join(assumptions)
        return answer, trip, validation_result

    # Extract params for planning
    params = normalize_trip_params(intent_agent(llm, standalone_request))

    # Merge with validated info
    if trip.get("origin") and not params.get("origin"):
        params["origin"] = trip["origin"]
    if trip.get("budget") and not params.get("budget_vnd"):
        params["budget_vnd"] = trip["budget"]
    if trip.get("people") and not params.get("adults"):
        params["adults"] = trip["people"]

    if params.get("origin_missing"):
        answer = "Hãy cung cấp cho tôi thêm thông tin về địa điểm xuất phát của bạn"
        return answer, trip, validation_result

    t0 = time.perf_counter()
    destination_options = destination_agent(llm, standalone_request, params)
    timings["destination_s"] = round(time.perf_counter() - t0, 2)

    if not destination_options:
        raise ValueError("Không tìm được địa điểm ứng viên phù hợp.")

    max_options = int(os.getenv("MAX_DESTINATION_OPTIONS", "3"))
    destination_options = destination_options[:max_options]

    t0 = time.perf_counter()
    destination_research = collect_research_for_destinations(
        params,
        destination_options,
    )
    timings["research_s"] = round(time.perf_counter() - t0, 2)

    t0 = time.perf_counter()
    answer = planning_agent(
        llm,
        standalone_request,
        params,
        destination_options,
        destination_research,
    )
    timings["planning_s"] = round(time.perf_counter() - t0, 2)

    from src.telemetry.metrics import tracker

    metadata = {
        "standalone_request": standalone_request,
        "params": params,
        "destination_options": destination_options,
        "timings": timings,
        "perf_stats": tracker.get_summary_stats(),
    }
    return answer, metadata

    # Clear trip after successful planning
    cleared_trip = {}

    return answer, cleared_trip, validation_result


def print_intro(history: list) -> None:
    print("=== Travel Planner Chatbot ===")
    print("Nhập yêu cầu du lịch. Gõ 'exit', 'quit' hoặc 'q' để thoát.")
    print(f"Lịch sử hội thoại: {HISTORY_PATH} ({len(history)} messages)")
    print("Ví dụ: Gợi ý chuyến đi biển cuối tuần tới")


def main() -> int:
    load_environment()
    store = load_history_store()
    history = get_active_messages(store)
    print_intro(history)

    # Simple state for multi-turn conversation
    current_trip = {}

    try:
        llm = create_llm_provider()
    except Exception as error:
        print(f"Lỗi khởi tạo LLM: {error}")
        return 1

    while True:
        user_input = input("\nBạn: ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("Tạm biệt.")
            return 0

        try:
            user_input = validate_user_input(user_input)
        except ValueError as validation_error:
            print(f"[Guardrail] {validation_error}")
            continue

        append_history(history, "user", user_input)
        append_message_to_active(store, "user", user_input)
        history = get_active_messages(store)

        try:
            standalone_request = rewrite_user_request(
                llm,
                history[:-1],
                user_input,
            )
            print("Đang xử lý yêu cầu:", standalone_request)
            answer, current_trip, validation_result = run_planner_turn(
                llm, standalone_request, current_trip
            )
        except Exception as error:
            logger.log_event("PIPELINE_ERROR", {"input": user_input, "error": str(error)})
            answer = f"Mình chưa xử lý được lượt này: {error}"
            current_trip = {}
            validation_result = None

        print("\nBot:")
        print(answer)
        append_message_to_active(store, "assistant", answer, metadata=metadata)
        history = get_active_messages(store)
        append_history(history, "assistant", answer, metadata={
            "validation": validation_result,
            "current_trip": current_trip,
        })


if __name__ == "__main__":
    raise SystemExit(main())
