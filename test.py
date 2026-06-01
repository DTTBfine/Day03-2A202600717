import json
import os
import re
import sys
from datetime import date

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal lab environments.
    load_dotenv = None

from src.tools.travel_api_tools import (
    estimate_transport_cost,
    get_weather,
    search_attractions,
    search_restaurants,
    search_stays,
)


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

    raise ValueError(
        f"Unsupported DEFAULT_PROVIDER={provider}. Use openai, google/gemini, or local."
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


def intent_agent(llm, user_request: str) -> dict:
    system_prompt = """
Bạn là bộ bóc tách yêu cầu du lịch.
Trả về DUY NHẤT một JSON object hợp lệ, không markdown, không giải thích.

Schema:
{
  "destination": "địa điểm đến cụ thể hoặc null nếu người dùng chỉ nói chung chung như đi biển/đi núi",
  "destination_candidates": ["các địa điểm cụ thể người dùng đã nêu hoặc bạn suy ra trực tiếp, có thể rỗng"],
  "origin": "điểm xuất phát hoặc null",
  "days": số ngày hoặc null,
  "budget_vnd": ngân sách VND hoặc null,
  "departure_date": "YYYY-MM-DD hoặc null",
  "return_date": "YYYY-MM-DD hoặc null",
  "adults": số người lớn, mặc định 1,
  "transport_mode": "flight|bus|train|car|null",
  "cuisine": "loại món/quán muốn tìm hoặc null",
  "theme": "beach|mountain|culture|food|relax|adventure|family|general",
  "constraints": ["ràng buộc/sở thích quan trọng từ yêu cầu"]
}

Quy đổi ngân sách tiếng Việt, ví dụ "5 triệu" thành 5000000.
Nếu người dùng nói "cuối tuần tới", hãy suy ra thứ 7 và chủ nhật gần nhất sau ngày hiện tại.
Nếu không chắc địa điểm cụ thể, để destination là null và ghi theme/constraints.
""".strip()

    response = llm.generate(
        f"Ngày hiện tại: {date.today().isoformat()}\nYêu cầu: {user_request}",
        system_prompt=system_prompt,
    )
    content = str(response.get("content", "")).strip()
    try:
        return _parse_json_object(content)
    except ValueError:
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

    system_prompt = """
Bạn là Destination Agent cho hệ thống lập kế hoạch du lịch Việt Nam.
Từ yêu cầu chung chung của user, hãy đề xuất 3-4 địa điểm cụ thể phù hợp.
Trả về DUY NHẤT JSON array hợp lệ, không markdown.

Mỗi item:
{
  "destination": "tên địa điểm cụ thể",
  "reason": "vì sao phù hợp với yêu cầu",
  "fit_tags": ["beach|mountain|food|relax|nearby|budget|weekend"],
  "suggested_transport_mode": "flight|bus|train|car|null"
}

Ưu tiên địa điểm ở Việt Nam, phù hợp số ngày/ngân sách/đi cuối tuần.
Không trả địa điểm chung chung như "đi biển"; phải là nơi cụ thể như "Đà Nẵng".
Nếu người dùng không nêu điểm xuất phát, để suggested_transport_mode là null và không ưu tiên theo tiêu chí "gần".
""".strip()
    prompt = json.dumps(
        {
            "today": date.today().isoformat(),
            "user_request": user_request,
            "extracted_params": params,
        },
        ensure_ascii=False,
        indent=2,
    )
    response = llm.generate(prompt, system_prompt=system_prompt)
    content = str(response.get("content", "")).strip()
    try:
        candidates = _parse_json_array(content)
    except ValueError:
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
    destination = destination_option["destination"]
    days = params["days"]
    transport_mode = (
        params.get("transport_mode")
        or destination_option.get("suggested_transport_mode")
        or "flight"
    )

    research = {
        "destination_option": destination_option,
        "weather": get_weather(destination, forecast_days=min(days, 7)),
        "attractions": search_attractions(
            destination,
            radius=10000,
            limit=min(6, max(3, days * 2)),
        ),
        "stays": search_stays(destination, radius=5000, limit=4),
        "restaurants": search_restaurants(
            destination,
            cuisine=params.get("cuisine"),
            radius=5000,
            limit=min(5, max(3, days * 2)),
        ),
        "transport": None,
    }

    if params.get("origin"):
        research["transport"] = estimate_transport_cost(
            origin=params["origin"],
            destination=destination,
            mode=transport_mode,
            departure_date=params.get("departure_date"),
            passengers=params["adults"],
        )

    return research


def collect_research_for_destinations(params: dict, destination_options: list) -> list:
    return [
        research_agent(destination_option, params)
        for destination_option in destination_options
    ]


def planning_agent(
    llm,
    user_request: str,
    params: dict,
    destination_options: list,
    destination_research: list,
) -> str:
    system_prompt = """
Bạn là Travel Planner Agent.
Nhiệm vụ: so sánh nhiều địa điểm và tổng hợp dữ liệu tool thành 1 hoặc nhiều phương án du lịch khả thi, có cấu trúc, bằng tiếng Việt.

Quy tắc:
- Chỉ dùng dữ liệu có trong tool observations, không bịa giá, tên khách sạn, nhà hàng hoặc thời tiết.
- Nếu dữ liệu thiếu/ước tính, nói rõ giới hạn.
- Mỗi phương án phải gắn với một địa điểm cụ thể và dữ liệu riêng của địa điểm đó.
- Nếu có nhiều địa điểm, hãy xếp hạng hoặc so sánh ngắn theo mức phù hợp với yêu cầu.
- Trả lời có cấu trúc: Tóm tắt yêu cầu, Bảng so sánh phương án, Chi tiết từng phương án, Lịch trình gợi ý, Ước tính ngân sách, Lưu ý.
- Với ngân sách, nêu mức còn lại sau chi phí di chuyển nếu có.
- Nếu không có dữ liệu transport vì user chưa nêu điểm xuất phát, ghi rõ "chưa ước tính vì thiếu điểm xuất phát"; không tự đoán phương tiện hay chi phí.
- Nếu transport là null ở một phương án, tuyệt đối không viết "ô tô", "máy bay", "xe khách" hoặc khoảng giá di chuyển cho phương án đó.
- Gợi ý thực tế, ngắn gọn, dễ làm theo.
""".strip()

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
    response = llm.generate(prompt, system_prompt=system_prompt)
    return str(response.get("content", "")).strip()


def main() -> int:
    load_environment()
    user_request = read_user_request()
    if not user_request:
        print("Bạn chưa nhập yêu cầu.")
        return 1

    try:
        llm = create_llm_provider()
        print("\nĐang bóc tách yêu cầu...", flush=True)
        params = normalize_trip_params(intent_agent(llm, user_request))

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
            f"Đang chạy tools riêng cho từng địa điểm: {destination_names}...",
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
