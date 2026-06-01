import time

import streamlit as st

from chatbot import (
    append_message_to_active,
    create_conversation,
    get_active_messages,
    get_conversations,
    load_history_store,
    reset_history_store,
    rewrite_user_request,
    save_history,
    validate_user_input,
    save_history_store,
    set_active_conversation,
)
from test import create_llm_provider, load_environment
from src.tools.travel_api_tools import validate_travel_input


st.set_page_config(
    page_title="Travel Planner Agent",
    page_icon="✈️",
    layout="centered",
)


@st.cache_resource
def get_llm():
    load_environment()
    return create_llm_provider()


def init_state() -> None:
    if "history_store" not in st.session_state:
        st.session_state.history_store = load_history_store()


def reset_history() -> None:
    st.session_state.history_store = reset_history_store()


def create_new_chat() -> None:
    create_conversation(st.session_state.history_store)
    save_history_store(st.session_state.history_store)
    if "history" not in st.session_state:
        st.session_state.history = load_history()
    if "current_trip" not in st.session_state:
        st.session_state.current_trip = {}


def reset_history() -> None:
    st.session_state.history = []
    st.session_state.current_trip = {}
    save_history([])


def render_history() -> None:
    messages = get_active_messages(st.session_state.history_store)
    if not messages:
        st.info("Chưa có tin nhắn trong hội thoại này.")
        return

    for message in messages:
        role = message.get("role", "assistant")
        content = message.get("content", "")
        if role not in {"user", "assistant"}:
            role = "assistant"
        with st.chat_message(role):
            st.markdown(content)
            if role == "assistant":
                total_s = message.get("metadata", {}).get("timings", {}).get("total_s")
                if total_s:
                    st.caption(f"Thời gian phản hồi: {total_s}s")


def handle_user_message(user_input: str) -> None:
    append_message_to_active(st.session_state.history_store, "user", user_input)

    total_start = time.perf_counter()
    rewrite_time = 0.0
    metadata = None

    try:
        llm = get_llm()

        t0 = time.perf_counter()
        messages = get_active_messages(st.session_state.history_store)
        standalone_request = rewrite_user_request(
            llm,
            messages[:-1],
            user_input,
        )
        rewrite_time = time.perf_counter() - t0

        with st.status("Đang xử lý yêu cầu...", expanded=True):
            st.write(f"Chuẩn hóa hội thoại ({rewrite_time:.1f}s): {standalone_request}")
            answer, metadata = run_planner_turn(llm, standalone_request)
            _render_timing_breakdown(metadata, rewrite_time)
    except Exception as error:
        answer = f"Mình chưa xử lý được lượt này: {error}"

    total_time = time.perf_counter() - total_start
    if metadata is None:
        metadata = {}
    metadata.setdefault("timings", {})
    metadata["timings"]["rewrite_s"] = round(rewrite_time, 2)
    metadata["timings"]["total_s"] = round(total_time, 2)
    st.session_state.last_timing = metadata["timings"]

    append_message_to_active(
        st.session_state.history_store,
        "assistant",
        answer,
        metadata=metadata,
    )


def conversation_label(index: int, conversation: dict) -> str:
    title = conversation.get("title") or "Hội thoại"
    count = len(conversation.get("messages", []))
    updated_at = conversation.get("updated_at", "")
    suffix = updated_at.replace("T", " ")[:16] if updated_at else ""
    return f"{index + 1}. {title} ({count}) {suffix}"


def render_sidebar() -> None:
    st.header("Lịch sử hội thoại")
    conversations = get_conversations(st.session_state.history_store)
    active_id = st.session_state.history_store.get("active_conversation_id")

    if not conversations:
        create_new_chat()
        conversations = get_conversations(st.session_state.history_store)
        active_id = st.session_state.history_store.get("active_conversation_id")

    labels = [
        conversation_label(index, conversation)
        for index, conversation in enumerate(conversations)
    ]
    ids = [conversation.get("id") for conversation in conversations]
    active_index = ids.index(active_id) if active_id in ids else 0

    selected_label = st.radio(
        "Chọn hội thoại",
        labels,
        index=active_index,
    )
    selected_index = labels.index(selected_label)
    selected_id = ids[selected_index]
    if selected_id != active_id:
        set_active_conversation(st.session_state.history_store, selected_id)
        save_history_store(st.session_state.history_store)
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Hội thoại mới", type="primary", use_container_width=True):
            create_new_chat()
            st.rerun()
    with col2:
        if st.button("Xóa tất cả", type="secondary", use_container_width=True):
            reset_history()
            st.rerun()

    active_messages = get_active_messages(st.session_state.history_store)
    st.caption(f"{len(conversations)} hội thoại, {len(active_messages)} tin nhắn đang mở")

    with st.expander("Xem cấu trúc lưu trữ", expanded=False):
        st.code("history.json -> conversations[] -> messages[]")


def _render_timing_breakdown(metadata: dict | None, rewrite_time: float) -> None:
    if not metadata:
        return
    t = metadata.get("timings", {})
    labels = [
        ("Ý định", t.get("intent_s")),
        ("Địa điểm", t.get("destination_s")),
        ("Thu thập dữ liệu", t.get("research_s")),
        ("Lập kế hoạch", t.get("planning_s")),
    ]
    available = [(label, val) for label, val in labels if val is not None]
    if not available:
        return
    cols = st.columns(len(available))
    for col, (label, val) in zip(cols, available):
        col.metric(label, f"{val}s")
        # Validate input
        validation_result = validate_travel_input(standalone_request)

        # Update current trip state
        current_trip = dict(st.session_state.current_trip)
        normalized = validation_result.get("normalized_input", {})
        if normalized.get("origin"):
            current_trip["origin"] = normalized["origin"]
        if normalized.get("destination"):
            current_trip["destination"] = normalized["destination"]
        if normalized.get("budget"):
            current_trip["budget"] = normalized["budget"]
        if normalized.get("people"):
            current_trip["people"] = normalized["people"]
        if normalized.get("days"):
            current_trip["days"] = normalized["days"]
        st.session_state.current_trip = current_trip

        with st.status("Đang xử lý yêu cầu...", expanded=False):
            st.write(f"Yêu cầu đã chuẩn hóa: {standalone_request}")

            # Check if validation passed
            if not validation_result["is_valid"]:
                follow_up = validation_result.get("follow_up_question", "")
                assumptions = validation_result.get("assumptions", [])

                st.warning("⚠️ Thiếu thông tin cần thiết:")
                if assumptions:
                    st.info("Giả định: " + "; ".join(assumptions))
                if follow_up:
                    st.info(follow_up)
                answer = follow_up or "Bạn cần cung cấp thêm thông tin."
            else:
                # Show assumptions if any
                if validation_result.get("assumptions"):
                    st.info("Giả định: " + "; ".join(validation_result["assumptions"]))

                # Run planning
                from chatbot import run_planner_turn
                answer, cleared_trip, _ = run_planner_turn(
                    llm, standalone_request, current_trip
                )
                st.session_state.current_trip = cleared_trip
    except Exception as error:
        answer = f"Mình chưa xử lý được lượt này: {error}"
        st.session_state.current_trip = {}

    append_history(st.session_state.history, "assistant", answer, metadata={
        "current_trip": st.session_state.current_trip,
    })


def main() -> None:
    init_state()

    st.title("Travel Planner Agent")
    st.caption("Chatbot gợi ý du lịch nhiều lượt, lưu từng cuộc hội thoại vào history.json")

    with st.sidebar:
        render_sidebar()

        if "last_timing" in st.session_state:
            t = st.session_state.last_timing
            st.divider()
            st.subheader("Lần phản hồi cuối")
            total_s = t.get("total_s")
            if total_s:
                st.metric("Tổng thời gian", f"{total_s}s")
            breakdown = [
                ("Chuẩn hóa", t.get("rewrite_s")),
                ("Ý định", t.get("intent_s")),
                ("Địa điểm", t.get("destination_s")),
                ("Dữ liệu", t.get("research_s")),
                ("Lập kế hoạch", t.get("planning_s")),
            ]
            for label, val in breakdown:
                if val is not None:
                    st.caption(f"{label}: {val}s")

    render_history()

    user_input = st.chat_input("Hãy nhập yêu cầu của bạn...")
    if user_input:
        try:
            user_input = validate_user_input(user_input)
        except ValueError as validation_error:
            st.warning(str(validation_error))
            st.stop()

        with st.chat_message("user"):
            st.markdown(user_input)

        handle_user_message(user_input)
        st.rerun()


if __name__ == "__main__":
    main()
