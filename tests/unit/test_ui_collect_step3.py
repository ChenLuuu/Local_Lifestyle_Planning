"""F02 unit tests: step-3 free text input + complete ConstraintSet submission."""

import pytest
from fastapi.testclient import TestClient

from agent.core.constraint_parser import parse_constraint_set
from agent.main import app
from agent.schemas import (
    CollectAllRequest,
    ConstraintSet,
    HardConstraints,
    SoftPreferences,
    Step1Answers,
    Step2Selections,
    Step3Input,
)

client = TestClient(app)


# ── helpers ────────────────────────────────────────────────────────────────────


def _s1(
    companion: str = "闺蜜",
    group_size: str = "3-4人",
    location: str = "市中心",
    scene: str = "美食之旅",
    budget: str = "100-200",
) -> Step1Answers:
    return Step1Answers(
        companion=companion,
        group_size=group_size,
        location=location,
        scene=scene,
        budget=budget,
    )


def _request(
    companion: str = "闺蜜",
    location: str = "市中心",
    budget: str = "100-200",
    tags: list[str] | None = None,
    special: str = "",
) -> CollectAllRequest:
    return CollectAllRequest(
        step1=_s1(companion=companion, location=location, budget=budget),
        step2=Step2Selections(tags=tags or []),
        step3=Step3Input(special_requirements=special),
    )


def _api_payload(
    companion: str = "闺蜜",
    location: str = "市中心",
    budget: str = "100-200",
    tags: list[str] | None = None,
    special: str = "",
) -> dict:
    return {
        "step1": {
            "companion": companion,
            "group_size": "3-4人",
            "location": location,
            "scene": "美食之旅",
            "budget": budget,
        },
        "step2": {"tags": tags or []},
        "step3": {"special_requirements": special},
    }


# ── Schema tests ───────────────────────────────────────────────────────────────


class TestSchemas:
    def test_step3_input_defaults_to_empty(self):
        s = Step3Input()
        assert s.special_requirements == ""

    def test_step3_input_accepts_text(self):
        s = Step3Input(special_requirements="宠物友好，不吃辣")
        assert "宠物友好" in s.special_requirements

    def test_hard_constraints_fields_exist(self):
        h = HardConstraints(max_distance_km=10.0, age_range=(18, 60), total_duration=4.0)
        assert h.max_distance_km == 10.0
        assert h.age_range == (18, 60)
        assert h.total_duration == 4.0

    def test_soft_preferences_fields_exist(self):
        s = SoftPreferences(noise_level="medium", per_capita=150, tags=["出片"])
        assert s.noise_level == "medium"
        assert s.per_capita == 150
        assert "出片" in s.tags

    def test_constraint_set_wraps_hard_and_soft(self):
        cs = ConstraintSet(
            hard=HardConstraints(max_distance_km=5.0, age_range=(0, 12), total_duration=3.0),
            soft=SoftPreferences(noise_level="low", per_capita=75, tags=[]),
        )
        assert cs.hard.max_distance_km == 5.0
        assert cs.soft.noise_level == "low"


# ── Hard constraint parsing ────────────────────────────────────────────────────


class TestHardConstraintParsing:
    @pytest.mark.parametrize(
        "location,expected_km",
        [
            ("市中心", 10.0),
            ("我家附近", 5.0),
            ("目的地周边", 3.0),
            ("随便", 20.0),
        ],
    )
    def test_location_maps_to_distance(self, location: str, expected_km: float):
        cs = parse_constraint_set(_request(location=location))
        assert cs.hard.max_distance_km == expected_km

    def test_unknown_location_defaults_to_10km(self):
        req = _request()
        req.step1.location = "火星"
        cs = parse_constraint_set(req)
        assert cs.hard.max_distance_km == 10.0

    @pytest.mark.parametrize(
        "companion,min_age,max_age",
        [
            ("带娃", 0, 12),
            ("家庭聚会", 0, 80),
            ("商务接待", 25, 65),
            ("闺蜜", 18, 40),
            ("兄弟", 18, 40),
        ],
    )
    def test_companion_maps_to_age_range(self, companion: str, min_age: int, max_age: int):
        cs = parse_constraint_set(_request(companion=companion))
        assert cs.hard.age_range == (min_age, max_age)

    def test_unknown_companion_defaults_age_range(self):
        req = _request()
        req.step1.companion = "外星人"
        cs = parse_constraint_set(req)
        assert cs.hard.age_range == (18, 60)

    def test_default_duration_is_4_hours(self):
        cs = parse_constraint_set(_request(special=""))
        assert cs.hard.total_duration == 4.0

    def test_duration_parsed_from_hours_text(self):
        cs = parse_constraint_set(_request(special="大概玩3小时"))
        assert cs.hard.total_duration == 3.0

    def test_half_day_maps_to_4_hours(self):
        cs = parse_constraint_set(_request(special="半天游"))
        assert cs.hard.total_duration == 4.0

    def test_full_day_maps_to_8_hours(self):
        cs = parse_constraint_set(_request(special="全天都有空"))
        assert cs.hard.total_duration == 8.0

    def test_decimal_duration_parsed(self):
        cs = parse_constraint_set(_request(special="大概2.5小时"))
        assert cs.hard.total_duration == 2.5


# ── Soft preference parsing ────────────────────────────────────────────────────


class TestSoftPreferenceParsing:
    @pytest.mark.parametrize(
        "budget,expected_per_capita",
        [
            ("人均<50", 50),
            ("50-100", 75),
            ("100-200", 150),
            ("200-500", 350),
            ("500+", 600),
        ],
    )
    def test_budget_maps_to_per_capita(self, budget: str, expected_per_capita: int):
        cs = parse_constraint_set(_request(budget=budget))
        assert cs.soft.per_capita == expected_per_capita

    def test_solo_companion_gives_low_noise(self):
        cs = parse_constraint_set(_request(companion="一个人"))
        assert cs.soft.noise_level == "low"

    def test_brother_companion_gives_high_noise(self):
        cs = parse_constraint_set(_request(companion="兄弟"))
        assert cs.soft.noise_level == "high"

    def test_default_noise_is_medium(self):
        cs = parse_constraint_set(_request(companion="闺蜜"))
        assert cs.soft.noise_level == "medium"

    def test_text_quiet_overrides_companion_noise(self):
        cs = parse_constraint_set(_request(companion="兄弟", special="想要安静的环境"))
        assert cs.soft.noise_level == "low"

    def test_text_lively_overrides_companion_noise(self):
        cs = parse_constraint_set(_request(companion="一个人", special="希望热闹一点"))
        assert cs.soft.noise_level == "high"

    def test_step2_tags_preserved_in_output(self):
        cs = parse_constraint_set(_request(tags=["出片", "美食"]))
        assert "出片" in cs.soft.tags
        assert "美食" in cs.soft.tags

    def test_pet_friendly_keyword_adds_tag(self):
        cs = parse_constraint_set(_request(special="最好宠物友好"))
        assert "宠物友好" in cs.soft.tags

    def test_spicy_keyword_adds_no_spicy_tag(self):
        cs = parse_constraint_set(_request(special="我不吃辣"))
        assert "不辣" in cs.soft.tags

    def test_student_keyword_adds_value_tag(self):
        cs = parse_constraint_set(_request(special="学生党预算有限"))
        assert "高性价比" in cs.soft.tags

    def test_step2_and_text_tags_merged_no_duplicates(self):
        cs = parse_constraint_set(
            _request(tags=["高性价比", "出片"], special="薅羊毛")
        )
        assert cs.soft.tags.count("高性价比") == 1

    def test_step2_tags_come_before_text_tags(self):
        cs = parse_constraint_set(_request(tags=["出片"], special="宠物友好"))
        assert cs.soft.tags.index("出片") < cs.soft.tags.index("宠物友好")


# ── API endpoint tests ─────────────────────────────────────────────────────────


class TestCollectCompleteEndpoint:
    def test_returns_200(self):
        resp = client.post("/api/collect/complete", json=_api_payload())
        assert resp.status_code == 200

    def test_status_is_collection_complete(self):
        resp = client.post("/api/collect/complete", json=_api_payload())
        assert resp.json()["status"] == "collection_complete"

    def test_response_contains_constraint_set(self):
        resp = client.post("/api/collect/complete", json=_api_payload())
        assert "constraint_set" in resp.json()

    def test_response_has_hard_and_soft_keys(self):
        resp = client.post("/api/collect/complete", json=_api_payload())
        cs = resp.json()["constraint_set"]
        assert "hard" in cs
        assert "soft" in cs

    def test_hard_fields_typed_correctly(self):
        resp = client.post("/api/collect/complete", json=_api_payload(location="我家附近"))
        hard = resp.json()["constraint_set"]["hard"]
        assert isinstance(hard["max_distance_km"], float)
        assert hard["max_distance_km"] == 5.0
        assert isinstance(hard["total_duration"], float)
        assert isinstance(hard["age_range"], list)

    def test_soft_tags_list_in_response(self):
        resp = client.post(
            "/api/collect/complete",
            json=_api_payload(tags=["出片", "美食"]),
        )
        tags = resp.json()["constraint_set"]["soft"]["tags"]
        assert isinstance(tags, list)
        assert "出片" in tags

    def test_full_flow_with_special_requirements(self):
        payload = _api_payload(
            companion="带娃",
            location="目的地周边",
            budget="50-100",
            tags=["亲子友好"],
            special="宠物友好，玩3小时",
        )
        resp = client.post("/api/collect/complete", json=payload)
        assert resp.status_code == 200
        cs = resp.json()["constraint_set"]
        assert cs["hard"]["max_distance_km"] == 3.0
        assert cs["hard"]["total_duration"] == 3.0
        assert cs["soft"]["per_capita"] == 75
        assert "亲子友好" in cs["soft"]["tags"]
        assert "宠物友好" in cs["soft"]["tags"]

    def test_empty_special_requirements_accepted(self):
        resp = client.post("/api/collect/complete", json=_api_payload(special=""))
        assert resp.status_code == 200

    def test_missing_step3_uses_default(self):
        payload = {
            "step1": {
                "companion": "闺蜜",
                "group_size": "2人",
                "location": "市中心",
                "scene": "元气打卡",
                "budget": "100-200",
            },
            "step2": {"tags": []},
            "step3": {},
        }
        resp = client.post("/api/collect/complete", json=payload)
        assert resp.status_code == 200
        assert resp.json()["constraint_set"]["hard"]["total_duration"] == 4.0
