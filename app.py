import streamlit as st

from chatbot import (
    append_history,
    load_history,
    rewrite_user_request,
    run_planner_turn,
    save_history,
)
from test import create_llm_provider, load_environment


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
    if "history" not in st.session_state:
        st.session_state.history = load_history()


def reset_history() -> None:
    st.session_state.history = []
    save_history([])


def render_history() -> None:
    for message in st.session_state.history:
        role = message.get("role", "assistant")
        content = message.get("content", "")
        if role not in {"user", "assistant"}:
            role = "assistant"
        with st.chat_message(role):
            st.markdown(content)


def handle_user_message(user_input: str) -> None:
    append_history(st.session_state.history, "user", user_input)

    try:
        llm = get_llm()
        standalone_request = rewrite_user_request(
            llm,
            st.session_state.history[:-1],
            user_input,
        )

        with st.status("Đang xử lý yêu cầu...", expanded=False):
            st.write(f"Yêu cầu đã chuẩn hóa: {standalone_request}")
            answer, metadata = run_planner_turn(llm, standalone_request)
    except Exception as error:
        answer = f"Mình chưa xử lý được lượt này: {error}"
        metadata = None

    append_history(st.session_state.history, "assistant", answer, metadata=metadata)


def main() -> None:
    init_state()

    st.title("Travel Planner Agent")
    st.caption("Chatbot gợi ý du lịch nhiều lượt, lưu lịch sử vào history.json")

    with st.sidebar:
        st.header("Lịch sử")
        st.write(f"{len(st.session_state.history)} tin nhắn")
        if st.button("Xóa lịch sử", type="secondary"):
            reset_history()
            st.rerun()
        st.divider()
        st.caption("Ví dụ")
        st.code("Gợi ý chuyến đi biển cuối tuần tới")
        st.code("từ Hà Nội")

    render_history()

    user_input = st.chat_input("Nhập yêu cầu du lịch của bạn...")
    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)

        handle_user_message(user_input)
        st.rerun()


if __name__ == "__main__":
    main()
