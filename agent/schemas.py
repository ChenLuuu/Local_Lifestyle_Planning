"""Pydantic request/response schemas for the Meituan Local Agent API."""

from typing import Any, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    value: str
    label: str


class CollectQuestion(BaseModel):
    id: str
    prompt: str
    options: list[QuestionOption]


class Step1Answers(BaseModel):
    companion: str
    group_size: str
    location: str
    scene: str
    budget: str
    duration: str = Field(default="")
    start_time: str = Field(default="")


class Step2Selections(BaseModel):
    tags: list[str] = Field(default_factory=list)


class TagsRequest(BaseModel):
    companion: str
    scene: str


class TagsResponse(BaseModel):
    tags: list[str]


class Step1And2Payload(BaseModel):
    step1: Step1Answers
    step2: Step2Selections


class Step1And2Response(BaseModel):
    status: str
    payload: Step1And2Payload


# ── F02: Step 3 + Complete ConstraintSet ──────────────────────────────────────


class Step3Input(BaseModel):
    special_requirements: str = Field(default="")


class HardConstraints(BaseModel):
    max_distance_km: float = Field(ge=0.0)
    age_range: tuple[int, int]  # [min_age, max_age]
    total_duration: float = Field(ge=0.5, le=24.0)  # hours


class SoftPreferences(BaseModel):
    noise_level: str  # "low" / "medium" / "high"
    per_capita: int = Field(ge=0)  # yuan
    tags: list[str] = Field(default_factory=list)


class RawLabels(BaseModel):
    location: str = ""
    companion: str = ""
    budget: str = ""
    scene: str = ""
    duration_text: str = ""
    start_time: str = ""


class ConstraintSet(BaseModel):
    hard: HardConstraints
    soft: SoftPreferences
    raw_labels: RawLabels = Field(default_factory=RawLabels)


class CollectAllRequest(BaseModel):
    step1: Step1Answers
    step2: Step2Selections
    step3: Step3Input
    user_id: str = Field(default="")


class CollectAllResponse(BaseModel):
    status: str
    constraint_set: ConstraintSet
    extracted_tags: list[str] = Field(default_factory=list)
    preference_summary: str = ""


# ── F03: Tool result TypedDicts ───────────────────────────────────────────────


class VenueResult(TypedDict):
    id: str
    name: str
    venue_type: str
    address: str
    per_capita: int
    duration_min: int
    tags: list[str]
    noise_level: str
    lat: float
    lng: float


class RestaurantResult(TypedDict):
    id: str
    name: str
    cuisine: str
    address: str
    per_capita: int
    duration_min: int
    tags: list[str]
    noise_level: str
    lat: float
    lng: float


class RouteResult(TypedDict):
    from_address: str
    to_address: str
    distance_km: float
    duration_min: int
    transit_mode: str


class AvailabilityResult(TypedDict):
    item_id: str
    available: bool
    next_slot: str | None


# ── F03: Itinerary Pydantic models ────────────────────────────────────────────


class TransitInfo(BaseModel):
    mode: str
    duration_min: int
    distance_km: float


class ItineraryNode(BaseModel):
    node_id: str
    node_type: str  # "restaurant" | "venue"
    name: str
    address: str
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    duration_min: int
    per_capita: int
    transit_to_next: TransitInfo | None = None


class Itinerary(BaseModel):
    session_id: str
    nodes: list[ItineraryNode]
    total_duration_min: int
    total_per_capita: int


class PlanRunRequest(BaseModel):
    constraint_set: ConstraintSet
    start_time: str = Field(default="10:00", pattern=r"^\d{2}:\d{2}$")
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = Field(default="")


# ── F03: SSE event envelope ───────────────────────────────────────────────────


class ReactEventData(TypedDict, total=False):
    type: str
    content: str
    tool: str
    params: dict[str, Any]
    result: dict[str, Any]
    itinerary: dict[str, Any]
    error: str


# ── F05: Node-swap (partial replan) ───────────────────────────────────────────


class SwapCandidatesRequest(BaseModel):
    session_id: str
    node_index: int = Field(ge=0)
    itinerary: Itinerary
    constraint_set: ConstraintSet


class SwapCandidatesResponse(BaseModel):
    session_id: str
    node_index: int
    candidates: list[ItineraryNode]


class SwapAcceptRequest(BaseModel):
    session_id: str
    node_index: int = Field(ge=0)
    candidate: ItineraryNode
    itinerary: Itinerary
    constraint_set: ConstraintSet


class SwapAcceptResponse(BaseModel):
    session_id: str
    itinerary: Itinerary


# ── F08: Collaborative confirmation ──────────────────────────────────────────


class CollabCreateRequest(BaseModel):
    itinerary: Itinerary
    owner_id: str
    member_ids: list[str]


class CollabCreateResponse(BaseModel):
    token: str
    expires_at: str
    share_url: str
    state: str


class CollabPlanResponse(BaseModel):
    token: str
    itinerary: Itinerary
    owner_id: str
    member_ids: list[str]
    contested_nodes: list[int]
    confirmed_users: list[str]
    state: str
    expires_at: str


class CollabVoteRequest(BaseModel):
    token: str
    user_id: str
    node_index: int = Field(ge=0)
    approved: bool
    comment: str = Field(default="")


class CollabResolveRequest(BaseModel):
    token: str
    replacement_map: dict[int, ItineraryNode]


class CollabConfirmRequest(BaseModel):
    token: str
    user_id: str


class CollabAdvanceRequest(BaseModel):
    token: str
    new_state: str


# ── F06: Execute Booking ───────────────────────────────────────────────────────


class ExecuteRequest(BaseModel):
    session_id: str
    itinerary: Itinerary
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))


class ExecuteEventData(TypedDict, total=False):
    type: str
    session_id: str
    total: int
    index: int
    node_id: str
    name: str
    status: str
    order_id: str
    message: str
    success_count: int
    failed_count: int
    confirmation_text: str


# ── F12: Commercial Touchpoints (deals / coupons) ─────────────────────────────


class DealItem(BaseModel):
    id: str
    title: str
    original_price: int
    deal_price: int
    savings: int
    category: str
    coupon_type: str
    valid_days: int


class NodeDeal(BaseModel):
    node_id: str
    node_name: str
    deals: list[DealItem]
    total_savings: int


class DealsMatchRequest(BaseModel):
    itinerary: Itinerary


class DealsMatchResponse(BaseModel):
    session_id: str
    node_deals: list[NodeDeal]
    total_savings: int
    summary: str  # "已为您节省 328 元"


# ── F13: Social Share Text Generation ────────────────────────────────────────


class ShareTextRequest(BaseModel):
    itinerary: Itinerary
    audience: str = Field(pattern=r"^(family|girlfriends|bros)$")


class ShareTextResponse(BaseModel):
    session_id: str
    audience: str
    title: str
    body: str
    hashtags: list[str]
    card_lines: list[str]


# ── User Flywheel: Profile + Auth + Preference Extraction ────────────────────


class UserProfile(BaseModel):
    user_id: str
    name: str = "小团"
    avatar: str = "🐻"
    preference_tags: list[str] = Field(default_factory=list)
    raw_notes: list[str] = Field(default_factory=list)
    preference_summary: str = ""


class LoginResponse(BaseModel):
    user_id: str
    name: str
    avatar: str
    preference_tags: list[str]
    preference_summary: str
    is_returning: bool


class ExtractPreferencesRequest(BaseModel):
    user_id: str
    free_text: str


class ExtractPreferencesResponse(BaseModel):
    extracted_tags: list[str]
    summary: str
    profile: UserProfile
