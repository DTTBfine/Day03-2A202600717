import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
import time
import asyncio
from datetime import date

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal lab environments.
    load_dotenv = None

from prompts import (
    CHECK_INTENT_PROMPT,
    DESTINATION_AGENT_PROMPT,
    INTENT_AGENT_PROMPT,
    PLANNING_AGENT_PROMPT,
)
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker
from src.tools.travel_api_tools import (
    estimate_transport_cost,
    get_weather,
    research_all_destinations_async,
    search_attractions,
    search_restaurants,
    search_stays,
    validate_travel_input,
)
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker


def load_environment() -> None:
    if load_dotenv:
        load_dotenv()
        return

    env_path = ".env"
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def create_llm_provider():
    provider = os.getenv("DEFAULT_PROVIDER", "openai").lower()
    model_name = os.getenv("DEFAULT_MODEL")

    if provider == "openai":
        from src.core.openai_provider import OpenAIProvider

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY in environment or .env")
        return OpenAIProvider(
            model_name=model_name or "gpt-4o",
            api_key=api_key,
        )

    if provider in {"google", "gemini"}:
        from src.core.gemini_provider import GeminiProvider

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Missing GEMINI_API_KEY in environment or .env")
        return GeminiProvider(
            model_name=model_name or "gemini-1.5-flash",
            api_key=api_key,
        )

    if provider == "local":
        from src.core.local_provider import LocalProvider

        model_path = os.getenv(
            "LOCAL_MODEL_PATH",
            "./models/Phi-3-mini-4k-instruct-q4.gguf",
        )
        return LocalProvider(model_path=model_path)

    if provider == "mimo":
        from src.core.mimo_provider import MimoProvider

        api_key = os.getenv("MIMO_API_KEY")
        if not api_key:
            raise ValueError("Missing MIMO_API_KEY in environment or .env")
        return MimoProvider(
            model_name=model_name or "mimo-v2.5-pro",
            api_key=api_key,
        )

    raise ValueError(
        f"Unsupported DEFAULT_PROVIDER={provider}. Use openai, google/gemini, local, or mimo."
    )


def read_user_request() -> str:
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()

    print("Nhập yêu cầu du lịch của bạn:")
    print("Ví dụ: Lập plan 3 ngày đi Đà Nẵng từ Hà Nội, ngân sách 5 triệu")
    return input("> ").strip()


GENERIC_DESTINATION_WORDS = {
    "biển",
    "núi",
    "rừng",
    "cao nguyên",
    "miền tây",
    "miền trung",
    "miền bắc",
    "miền nam",
    "đảo",
    "du lịch",
    "nghỉ dưỡng",
}

def check_intent(llm, user_request: str) -> str:
    """
    Kiểm tra xem người dùng đã cung cấp địa điểm xuất phát chưa.
    Returns "Có" hoặc "Không".
    """
    response = llm.generate(
        f"Yêu cầu: {user_request}",
        system_prompt=CHECK_INTENT_PROMPT,
    )

    content = str(response.get("content", "")).strip()

    try:
        data = _parse_json_object(content)
        return "Có" if data.get("has_origin") is True else "Không"
    except Exception:
        return "Không"

def intent_agent(llm, user_request: str) -> dict:
    response = llm.generate(
        f"Ngày hiện tại: {date.today().isoformat()}\nYêu cầu: {user_request}",
        system_prompt=INTENT_AGENT_PROMPT,
    )
    tracker.track_request(
        provider=response.get("provider", getattr(llm, "provider_name", "unknown")),
        model=getattr(llm, "model_name", "unknown"),
        usage=response.get("usage", {}),
        latency_ms=response.get("latency_ms", 0),
        agent_name="intent_agent",
    )
    content = str(response.get("content", "")).strip()
    try:
        return _parse_json_object(content)
    except ValueError:
        logger.log_event("PIPELINE_PARSE_ERROR", {"agent": "intent_agent", "raw": content[:500]})
        return _fallback_extract(user_request)


def _parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def _fallback_extract(user_request: str) -> dict:
    days_match = re.search(r"(\d+)\s*ngày", user_request, flags=re.IGNORECASE)
    budget_match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*(triệu|tr|k|nghìn|ngàn)?",
        user_request,
        flags=re.IGNORECASE,
    )
    destination = None
    destination_match = re.search(
        r"(?:đi|tới|đến)\s+([^,]+?)(?:\s+từ|\s+ngân sách|$)",
        user_request,
        flags=re.IGNORECASE,
    )
    if destination_match:
        destination = destination_match.group(1).strip()
        if _is_generic_destination(destination):
            destination = None

    origin = None
    origin_match = re.search(
        r"từ\s+([^,]+?)(?:\s+ngân sách|$)",
        user_request,
        flags=re.IGNORECASE,
    )
    if origin_match:
        origin = origin_match.group(1).strip()

    budget_vnd = None
    if budget_match:
        number = float(budget_match.group(1).replace(",", "."))
        unit = (budget_match.group(2) or "").lower()
        if unit in {"triệu", "tr"}:
            budget_vnd = int(number * 1_000_000)
        elif unit in {"k", "nghìn", "ngàn"}:
            budget_vnd = int(number * 1_000)

    return {
        "destination": destination,
        "destination_candidates": [],
        "origin": origin,
        "days": int(days_match.group(1)) if days_match else 3,
        "budget_vnd": budget_vnd,
        "departure_date": None,
        "return_date": None,
        "adults": 1,
        "transport_mode": None,
        "cuisine": None,
        "theme": _infer_theme(user_request),
        "constraints": [],
    }


def normalize_trip_params(params: dict) -> dict:
    days = params.get("days") or 3
    adults = params.get("adults") or 1
    destination = params.get("destination")
    origin = params.get("origin")
    if destination and _is_generic_destination(str(destination)):
        destination = None
    if origin:
        origin = str(origin).strip()

    return {
        "destination": str(destination).strip() if destination else None,
        "destination_candidates": _normalize_candidate_names(
            params.get("destination_candidates") or []
        ),
        "origin": origin,
        "origin_missing": not bool(origin),
        "days": max(1, min(int(days), 10)),
        "budget_vnd": params.get("budget_vnd"),
        "departure_date": params.get("departure_date"),
        "return_date": params.get("return_date"),
        "adults": max(1, int(adults)),
        "transport_mode": params.get("transport_mode"),
        "cuisine": params.get("cuisine"),
        "theme": params.get("theme") or "general",
        "constraints": params.get("constraints") or [],
    }


def _is_generic_destination(destination: str) -> bool:
    normalized = destination.lower().strip()
    return any(word in normalized for word in GENERIC_DESTINATION_WORDS)


def _infer_theme(user_request: str) -> str:
    lowered = user_request.lower()
    if "biển" in lowered or "đảo" in lowered:
        return "beach"
    if "núi" in lowered or "rừng" in lowered:
        return "mountain"
    if "ăn" in lowered or "ẩm thực" in lowered:
        return "food"
    if "nghỉ" in lowered or "relax" in lowered:
        return "relax"
    return "general"


def _normalize_candidate_names(candidates) -> list:
    names = []
    for item in candidates:
        if isinstance(item, dict):
            name = item.get("destination") or item.get("name")
        else:
            name = item
        if not name:
            continue
        name = str(name).strip()
        if name and name not in names and not _is_generic_destination(name):
            names.append(name)
    return names[:5]


def destination_agent(llm, user_request: str, params: dict) -> list:
    if params.get("destination"):
        return [
            {
                "destination": params["destination"],
                "reason": "Địa điểm cụ thể do người dùng yêu cầu.",
                "fit_tags": [params.get("theme") or "general"],
            }
        ]

    if params.get("destination_candidates"):
        return [
            {
                "destination": destination,
                "reason": "Địa điểm ứng viên được bóc tách từ yêu cầu.",
                "fit_tags": [params.get("theme") or "general"],
            }
            for destination in params["destination_candidates"][:4]
        ]

    prompt = json.dumps(
        {
            "today": date.today().isoformat(),
            "user_request": user_request,
            "extracted_params": params,
        },
        ensure_ascii=False,
        indent=2,
    )
    response = llm.generate(prompt, system_prompt=DESTINATION_AGENT_PROMPT)
    tracker.track_request(
        provider=response.get("provider", getattr(llm, "provider_name", "unknown")),
        model=getattr(llm, "model_name", "unknown"),
        usage=response.get("usage", {}),
        latency_ms=response.get("latency_ms", 0),
        agent_name="destination_agent",
    )
    content = str(response.get("content", "")).strip()
    try:
        candidates = _parse_json_array(content)
    except ValueError:
        logger.log_event("PIPELINE_PARSE_ERROR", {"agent": "destination_agent", "raw": content[:500]})
        candidates = _fallback_destination_candidates(params)

    normalized = []
    for item in candidates:
        if isinstance(item, str):
            item = {"destination": item, "reason": "Phù hợp với yêu cầu chung.", "fit_tags": []}
        destination = item.get("destination") or item.get("name")
        if not destination or _is_generic_destination(str(destination)):
            continue
        normalized.append(
            {
                "destination": str(destination).strip(),
                "reason": item.get("reason") or "Phù hợp với yêu cầu chung.",
                "fit_tags": item.get("fit_tags") or [params.get("theme") or "general"],
                "suggested_transport_mode": item.get("suggested_transport_mode")
                if params.get("origin")
                else None,
            }
        )
    return normalized[:4]


def _parse_json_array(text: str) -> list:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON array found")
    value = json.loads(match.group(0))
    if not isinstance(value, list):
        raise ValueError("JSON value is not an array")
    return value


def _fallback_destination_candidates(params: dict) -> list:
    theme = params.get("theme")
    if theme == "beach":
        names = ["Đà Nẵng", "Nha Trang", "Quy Nhơn", "Phú Quốc"]
    elif theme == "mountain":
        names = ["Đà Lạt", "Sa Pa", "Mộc Châu", "Tam Đảo"]
    else:
        names = ["Đà Nẵng", "Đà Lạt", "Nha Trang", "Huế"]
    return [
        {
            "destination": name,
            "reason": "Địa điểm fallback phù hợp yêu cầu chung.",
            "fit_tags": [theme or "general"],
        }
        for name in names
    ]


def research_agent(destination_option: dict, params: dict) -> dict:
    """Sync wrapper for backward compatibility - calls async version."""
    destination = destination_option["destination"]
    days = params["days"]
    transport_mode = (
        params.get("transport_mode")
        or destination_option.get("suggested_transport_mode")
        or "flight"
    )

    with ThreadPoolExecutor() as executor:
        future_weather = executor.submit(get_weather, destination, min(days, 7))
        future_attractions = executor.submit(
            search_attractions, destination, 10000, min(6, max(3, days * 2))
        )
        future_stays = executor.submit(search_stays, destination, 5000, 4)
        future_restaurants = executor.submit(
            search_restaurants,
            destination,
            params.get("cuisine"),
            5000,
            min(5, max(3, days * 2)),
        )
        future_transport = (
            executor.submit(
                estimate_transport_cost,
                origin=params["origin"],
                destination=destination,
                mode=transport_mode,
                departure_date=params.get("departure_date"),
                passengers=params["adults"],
            )
            if params.get("origin")
            else None
        )

        return {
            "destination_option": destination_option,
            "weather": future_weather.result(),
            "attractions": future_attractions.result(),
            "stays": future_stays.result(),
            "restaurants": future_restaurants.result(),
            "transport": future_transport.result() if future_transport else None,
        }


def collect_research_for_destinations(params: dict, destination_options: list) -> list:
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(research_agent, option, params)
            for option in destination_options
        ]
        return [f.result() for f in futures]

    # Use async research for better performance
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            research_destination_async(destination, params, destination_option)
        )
        return {
            "destination_option": destination_option,
            "weather": result.get("tool_results", {}).get("weather", {}),
            "attractions": result.get("tool_results", {}).get("attractions", {}),
            "stays": result.get("tool_results", {}).get("stays", {}),
            "restaurants": result.get("tool_results", {}).get("restaurants", {}),
            "transport": result.get("tool_results", {}).get("transport"),
            "research_latency_ms": result.get("research_latency_ms", 0),
            "errors": result.get("errors", []),
        }
    finally:
        loop.close()


def collect_research_for_destinations(params: dict, destination_options: list) -> list:
    """Collect research for all destinations using async parallel execution."""
    start_time = time.time()

    # Run async research in new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async_results = loop.run_until_complete(
            research_all_destinations_async(destination_options, params)
        )
    finally:
        loop.close()

    # Convert async results to format expected by planning_agent
    results = []
    for result in async_results:
        tool_results = result.get("tool_results", {})
        results.append({
            "destination_option": result.get("destination_option", {}),
            "weather": tool_results.get("weather", {}),
            "attractions": tool_results.get("attractions", {}),
            "stays": tool_results.get("stays", {}),
            "restaurants": tool_results.get("restaurants", {}),
            "transport": tool_results.get("transport"),
            "research_latency_ms": result.get("research_latency_ms", 0),
            "errors": result.get("errors", []),
        })

    # Log metrics
    total_latency_ms = int((time.time() - start_time) * 1000)
    logger.log_event("ASYNC_RESEARCH_COMPLETE", {
        "destinations_count": len(destination_options),
        "total_latency_ms": total_latency_ms,
        "errors_count": sum(len(r.get("errors", [])) for r in results),
    })

    return results


def planning_agent(
    llm,
    user_request: str,
    params: dict,
    destination_options: list,
    destination_research: list,
) -> str:
    prompt = json.dumps(
        {
            "user_request": user_request,
            "extracted_params": params,
            "destination_options": destination_options,
            "destination_research": destination_research,
        },
        ensure_ascii=False,
        indent=2,
    )
    response = llm.generate(prompt, system_prompt=PLANNING_AGENT_PROMPT)
    tracker.track_request(
        provider=response.get("provider", getattr(llm, "provider_name", "unknown")),
        model=getattr(llm, "model_name", "unknown"),
        usage=response.get("usage", {}),
        latency_ms=response.get("latency_ms", 0),
        agent_name="planning_agent",
    )
    return str(response.get("content", "")).strip()


def main() -> int:
    load_environment()
    user_request = read_user_request()
    if not user_request:
        print("Bạn chưa nhập yêu cầu.")
        return 1

    try:
        # Step 0: Validate input
        print("\nĐang kiểm tra thông tin yêu cầu...", flush=True)
        validation_result = validate_travel_input(user_request)
        logger.log_event("VALIDATION_RESULT", {
            "is_valid": validation_result["is_valid"],
            "missing_fields": validation_result.get("missing_fields", []),
            "assumptions": validation_result.get("assumptions", []),
            "user_message": user_request,
        })

        if not validation_result["is_valid"]:
            follow_up = validation_result.get("follow_up_question", "")
            assumptions = validation_result.get("assumptions", [])
            print("\n⚠️ Thiếu thông tin cần thiết:")
            if assumptions:
                print("Giả định:")
                for a in assumptions:
                    print(f"  - {a}")
            print(f"\n{follow_up}")
            return 1

        # Show assumptions if any
        if validation_result.get("assumptions"):
            print("ℹ️ Giả định:")
            for a in validation_result["assumptions"]:
                print(f"  - {a}")

        llm = create_llm_provider()

        intent = check_intent(llm, user_request)
        if intent == "Không":
            answer ="Hãy cho tôi biết thêm thông tin về địa điểm xuất phát của bạn để tôi có thể gợi ý lịch trình phù hợp nhất"
            print(answer)
            return 0
        
        print("\nĐang bóc tách yêu cầu...", flush=True)
        params = normalize_trip_params(intent_agent(llm, user_request))

        # Merge normalized input from validation with params
        normalized = validation_result.get("normalized_input", {})
        if normalized.get("origin") and not params.get("origin"):
            params["origin"] = normalized["origin"]
        if normalized.get("budget") and not params.get("budget_vnd"):
            params["budget_vnd"] = normalized["budget"]
        if normalized.get("people") and not params.get("adults"):
            params["adults"] = normalized["people"]
        if normalized.get("days") and not params.get("days"):
            params["days"] = normalized["days"]

        print("Đang tìm các địa điểm phù hợp...", flush=True)
        destination_options = destination_agent(llm, user_request, params)
        if not destination_options:
            raise ValueError("Không tìm được địa điểm ứng viên phù hợp.")
        max_options = int(os.getenv("MAX_DESTINATION_OPTIONS", "3"))
        destination_options = destination_options[:max_options]

        destination_names = ", ".join(
            option["destination"] for option in destination_options
        )
        print(
            f"Đang chạy tools song song cho từng địa điểm: {destination_names}...",
            flush=True,
        )
        destination_research = collect_research_for_destinations(
            params,
            destination_options,
        )

        print("Đang dùng LLM so sánh và tổng hợp các plan khả thi...\n", flush=True)
        answer = planning_agent(
            llm,
            user_request,
            params,
            destination_options,
            destination_research,
        )
    except Exception as error:
        print(f"Lỗi khi chạy travel planner: {error}")
        return 1

    print("=== PLAN GỢI Ý ===")
    print(answer)
    return 0


if __name__ == "__main__": 
    raise SystemExit(main())
