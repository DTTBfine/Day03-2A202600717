import json
import os
from datetime import datetime

from test import (
    collect_research_for_destinations,
    create_llm_provider,
    destination_agent,
    intent_agent,
    load_environment,
    normalize_trip_params,
    planning_agent,
)


HISTORY_PATH = "history.json"
MAX_HISTORY_MESSAGES = 8


def load_history() -> list:
    if not os.path.exists(HISTORY_PATH):
        return []

    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as history_file:
            data = json.load(history_file)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(data, list):
        return []
    return data


def save_history(history: list) -> None:
    with open(HISTORY_PATH, "w", encoding="utf-8") as history_file:
        json.dump(history, history_file, ensure_ascii=False, indent=2)


def append_history(history: list, role: str, content: str, metadata: dict = None) -> None:
    item = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
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


def rewrite_user_request(llm, history: list, user_input: str) -> str:
    if not history:
        return user_input

    system_prompt = """
Bạn là bộ chuẩn hóa hội thoại cho travel planner.
Nhiệm vụ: dựa trên lịch sử hội thoại và tin nhắn mới nhất, viết lại thành một yêu cầu du lịch đầy đủ, độc lập.

Quy tắc:
- Giữ nguyên các thông tin quan trọng đã có: điểm đến/chủ đề, điểm xuất phát, số ngày, ngân sách, ngày đi, sở thích.
- Nếu user chỉ bổ sung một thông tin như "từ Hà Nội", hãy ghép nó vào yêu cầu du lịch trước đó.
- Nếu assistant vừa hỏi điểm xuất phát và user trả lời địa điểm xuất phát, hãy ghép địa điểm đó vào yêu cầu du lịch gần nhất.
- Không bịa thông tin chưa có.
- Trả về DUY NHẤT nội dung yêu cầu đã viết lại, không markdown, không giải thích.
""".strip()
    prompt = json.dumps(
        {
            "recent_dialogue": recent_dialogue(history),
            "new_user_message": user_input,
        },
        ensure_ascii=False,
        indent=2,
    )
    response = llm.generate(prompt, system_prompt=system_prompt)
    rewritten = str(response.get("content", "")).strip()
    return rewritten or user_input


def run_planner_turn(llm, standalone_request: str) -> tuple:
    params = normalize_trip_params(intent_agent(llm, standalone_request))
    if params.get("origin_missing"):
        answer = "Hãy cung cấp cho tôi thêm thông tin về địa điểm xuất phát của bạn"
        metadata = {
            "standalone_request": standalone_request,
            "params": params,
            "needs_origin": True,
        }
        return answer, metadata

    destination_options = destination_agent(llm, standalone_request, params)
    if not destination_options:
        raise ValueError("Không tìm được địa điểm ứng viên phù hợp.")

    max_options = int(os.getenv("MAX_DESTINATION_OPTIONS", "3"))
    destination_options = destination_options[:max_options]
    destination_research = collect_research_for_destinations(
        params,
        destination_options,
    )
    answer = planning_agent(
        llm,
        standalone_request,
        params,
        destination_options,
        destination_research,
    )
    metadata = {
        "standalone_request": standalone_request,
        "params": params,
        "destination_options": destination_options,
    }
    return answer, metadata


def print_intro(history: list) -> None:
    print("=== Travel Planner Chatbot ===")
    print("Nhập yêu cầu du lịch. Gõ 'exit', 'quit' hoặc 'q' để thoát.")
    print(f"Lịch sử hội thoại: {HISTORY_PATH} ({len(history)} messages)")
    print("Ví dụ: Gợi ý chuyến đi biển cuối tuần tới")


def main() -> int:
    load_environment()
    history = load_history()
    print_intro(history)

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

        append_history(history, "user", user_input)

        try:
            standalone_request = rewrite_user_request(
                llm,
                history[:-1],
                user_input,
            )
            print("Đang xử lý yêu cầu:", standalone_request)
            answer, metadata = run_planner_turn(llm, standalone_request)
        except Exception as error:
            answer = f"Mình chưa xử lý được lượt này: {error}"
            metadata = None

        print("\nBot:")
        print(answer)
        append_history(history, "assistant", answer, metadata=metadata)


if __name__ == "__main__":
    raise SystemExit(main())
