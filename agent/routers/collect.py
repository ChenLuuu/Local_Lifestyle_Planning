"""Router: progressive constraint collection — steps 1 & 2 (F01)."""

from fastapi import APIRouter

from agent.core.constraint_parser import get_suggested_tags, parse_constraint_set
from agent.modules.preference_extractor import extract_preferences
from agent.modules.profile_store import get_profile, merge_tags
from agent.schemas import (
    CollectAllRequest,
    CollectAllResponse,
    CollectQuestion,
    QuestionOption,
    Step1And2Payload,
    Step1And2Response,
    TagsRequest,
    TagsResponse,
)

router = APIRouter(prefix="/api/collect", tags=["collect"])


def _make_options(values: list[str]) -> list[QuestionOption]:
    return [QuestionOption(value=v, label=v) for v in values]


QUESTIONS: list[CollectQuestion] = [
    CollectQuestion(
        id="companion",
        prompt="这次和谁一起？",
        options=_make_options(
            ["一个人", "另一半", "闺蜜", "兄弟", "带娃", "家庭聚会", "商务接待"]
        ),
    ),
    CollectQuestion(
        id="group_size",
        prompt="一共几位？",
        options=_make_options(["1人", "2人", "3-4人", "5人以上"]),
    ),
    CollectQuestion(
        id="location",
        prompt="想在哪一带玩？",
        options=_make_options(["市中心", "我家附近", "目的地周边", "随便"]),
    ),
    CollectQuestion(
        id="scene",
        prompt="今天想要什么感觉？",
        options=_make_options(
            ["悠闲放松", "元气打卡", "文化探索", "美食之旅", "仪式感出行", "商务接待"]
        ),
    ),
    CollectQuestion(
        id="budget",
        prompt="人均预算大概多少？",
        options=_make_options(["人均<50", "50-100", "100-200", "200-500", "500+"]),
    ),
    CollectQuestion(
        id="duration",
        prompt="打算玩多久？",
        options=_make_options(
            ["2小时", "半天（4小时）", "大半天（6小时）", "全天（8小时）"]
        ),
    ),
    CollectQuestion(
        id="start_time",
        prompt="几点出发？",
        options=_make_options(["上午 10:00", "上午 11:00", "下午 14:00", "傍晚 17:00"]),
    ),
]


@router.get("/questions", response_model=list[CollectQuestion])
async def get_questions() -> list[CollectQuestion]:
    """Return the step-1 single-choice question sequence."""
    return QUESTIONS


@router.post("/tags", response_model=TagsResponse)
async def get_tags(body: TagsRequest) -> TagsResponse:
    """Generate step-2 word-cloud tag suggestions from step-1 answers."""
    return get_suggested_tags(body)


@router.post("/step1_2", response_model=Step1And2Response)
async def submit_step1_2(payload: Step1And2Payload) -> Step1And2Response:
    """Receive combined step 1+2 data; persisted for step 3 in F02."""
    return Step1And2Response(status="step1_2_complete", payload=payload)


@router.post("/complete", response_model=CollectAllResponse)
async def submit_complete(body: CollectAllRequest) -> CollectAllResponse:
    """Merge all three steps into a ConstraintSet and hand off to the planning Agent.

    When user_id is provided, extract preferences from free text via LLM,
    merge them into the user profile, and enrich the constraint set tags.
    """
    constraint_set = parse_constraint_set(body)

    extracted_tags: list[str] = []
    summary = ""

    free_text = body.step3.special_requirements.strip()
    if body.user_id and free_text:
        extracted_tags, summary = await extract_preferences(free_text)
        if extracted_tags:
            merge_tags(body.user_id, extracted_tags, note=free_text)
            # Enrich soft tags with profile preferences
            profile = get_profile(body.user_id)
            merged = list(
                dict.fromkeys([*constraint_set.soft.tags, *profile.preference_tags])
            )
            constraint_set.soft.tags = merged

    return CollectAllResponse(
        status="collection_complete",
        constraint_set=constraint_set,
        extracted_tags=extracted_tags,
        preference_summary=summary,
    )
