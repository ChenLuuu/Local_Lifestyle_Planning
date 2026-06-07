"""F01 unit tests: step-1 single-choice + step-2 word-cloud multi-select."""

import pytest
from fastapi.testclient import TestClient

from agent.core.constraint_parser import get_suggested_tags
from agent.main import app
from agent.schemas import (
    Step1And2Payload,
    Step1Answers,
    Step2Selections,
    TagsRequest,
)

client = TestClient(app)


def _valid_step1():
    return {
        "companion": "闺蜜",
        "group_size": "3-4人",
        "location": "市中心",
        "scene": "美食之旅",
        "budget": "100-200",
    }


class TestGetQuestions:
    def test_returns_seven_questions(self):
        resp = client.get("/api/collect/questions")
        assert resp.status_code == 200
        assert len(resp.json()) == 7

    def test_question_ids_in_order(self):
        resp = client.get("/api/collect/questions")
        ids = [q["id"] for q in resp.json()]
        assert ids == [
            "companion", "group_size", "location", "scene", "budget", "duration", "start_time"
        ]

    def test_each_question_has_prompt_and_options(self):
        resp = client.get("/api/collect/questions")
        for q in resp.json():
            assert "prompt" in q
            assert len(q["options"]) >= 2

    def test_option_has_value_and_label(self):
        resp = client.get("/api/collect/questions")
        companion_q = next(q for q in resp.json() if q["id"] == "companion")
        for opt in companion_q["options"]:
            assert "value" in opt
            assert "label" in opt

    def test_companion_has_seven_options(self):
        resp = client.get("/api/collect/questions")
        companion_q = next(q for q in resp.json() if q["id"] == "companion")
        assert len(companion_q["options"]) == 7

    def test_companion_options_cover_all_types(self):
        resp = client.get("/api/collect/questions")
        companion_q = next(q for q in resp.json() if q["id"] == "companion")
        values = {o["value"] for o in companion_q["options"]}
        assert {"闺蜜", "带娃", "商务接待", "另一半", "兄弟"}.issubset(values)

    def test_budget_question_has_five_tiers(self):
        resp = client.get("/api/collect/questions")
        budget_q = next(q for q in resp.json() if q["id"] == "budget")
        assert len(budget_q["options"]) == 5

    def test_duration_question_has_four_options(self):
        resp = client.get("/api/collect/questions")
        duration_q = next(q for q in resp.json() if q["id"] == "duration")
        assert len(duration_q["options"]) == 4
        values = {o["value"] for o in duration_q["options"]}
        assert {"2小时", "半天（4小时）", "大半天（6小时）", "全天（8小时）"} == values

    def test_start_time_question_has_four_options(self):
        resp = client.get("/api/collect/questions")
        st_q = next(q for q in resp.json() if q["id"] == "start_time")
        assert len(st_q["options"]) == 4
        values = {o["value"] for o in st_q["options"]}
        assert {"上午 10:00", "上午 11:00", "下午 14:00", "傍晚 17:00"} == values


class TestGetTags:
    def test_friend_companion_returns_expected_tags(self):
        resp = client.post(
            "/api/collect/tags",
            json={"companion": "闺蜜", "scene": "美食之旅"},
        )
        assert resp.status_code == 200
        tags = resp.json()["tags"]
        assert "出片" in tags
        assert "美食" in tags

    def test_family_with_child_returns_child_friendly_tags(self):
        resp = client.post(
            "/api/collect/tags",
            json={"companion": "带娃", "scene": "悠闲放松"},
        )
        tags = resp.json()["tags"]
        assert "亲子友好" in tags
        assert "儿童乐园" in tags

    def test_business_companion_returns_professional_tags(self):
        resp = client.post(
            "/api/collect/tags",
            json={"companion": "商务接待", "scene": "商务接待"},
        )
        tags = resp.json()["tags"]
        assert "高端大气" in tags

    def test_no_duplicate_tags_in_response(self):
        resp = client.post(
            "/api/collect/tags",
            json={"companion": "商务接待", "scene": "商务接待"},
        )
        tags = resp.json()["tags"]
        assert len(tags) == len(set(tags))

    def test_unknown_companion_still_returns_scene_tags(self):
        result = get_suggested_tags(TagsRequest(companion="外星人", scene="悠闲放松"))
        assert "慢节奏" in result.tags

    def test_scene_tags_appended_to_companion_tags(self):
        result = get_suggested_tags(TagsRequest(companion="闺蜜", scene="元气打卡"))
        tags = result.tags
        # 闺蜜 tags: 出片 美食 艺术 美甲 购物 不想走路 室内
        # 元气打卡 tags: 网红地标 光线好 出片角度 (出片角度 ≠ 出片, no collision)
        assert "出片" in tags
        assert "网红地标" in tags
        assert tags.index("出片") < tags.index("网红地标")

    def test_tags_response_is_list(self):
        resp = client.post(
            "/api/collect/tags",
            json={"companion": "一个人", "scene": "文化探索"},
        )
        assert isinstance(resp.json()["tags"], list)


class TestSubmitStep1And2:
    def _payload(self, tags=None):
        return {
            "step1": _valid_step1(),
            "step2": {"tags": tags if tags is not None else ["出片", "美食"]},
        }

    def test_submit_returns_200(self):
        resp = client.post("/api/collect/step1_2", json=self._payload())
        assert resp.status_code == 200

    def test_submit_status_is_step1_2_complete(self):
        resp = client.post("/api/collect/step1_2", json=self._payload())
        assert resp.json()["status"] == "step1_2_complete"

    def test_submit_echoes_companion(self):
        resp = client.post("/api/collect/step1_2", json=self._payload())
        assert resp.json()["payload"]["step1"]["companion"] == "闺蜜"

    def test_submit_echoes_all_step1_fields(self):
        resp = client.post("/api/collect/step1_2", json=self._payload())
        step1 = resp.json()["payload"]["step1"]
        assert step1["group_size"] == "3-4人"
        assert step1["location"] == "市中心"
        assert step1["scene"] == "美食之旅"
        assert step1["budget"] == "100-200"

    def test_submit_echoes_tags(self):
        resp = client.post(
            "/api/collect/step1_2",
            json=self._payload(tags=["出片", "美食", "美甲"]),
        )
        assert resp.json()["payload"]["step2"]["tags"] == ["出片", "美食", "美甲"]

    def test_submit_with_empty_tags_is_valid(self):
        resp = client.post("/api/collect/step1_2", json=self._payload(tags=[]))
        assert resp.status_code == 200

    def test_pydantic_model_step1_validates(self):
        answers = Step1Answers(
            companion="闺蜜",
            group_size="2人",
            location="市中心",
            scene="元气打卡",
            budget="100-200",
        )
        assert answers.companion == "闺蜜"

    def test_pydantic_payload_round_trip(self):
        payload = Step1And2Payload(
            step1=Step1Answers(
                companion="带娃",
                group_size="3-4人",
                location="我家附近",
                scene="悠闲放松",
                budget="50-100",
            ),
            step2=Step2Selections(tags=["亲子友好", "儿童乐园"]),
        )
        assert payload.step1.companion == "带娃"
        assert "亲子友好" in payload.step2.tags

    def test_step2_default_tags_is_empty_list(self):
        sel = Step2Selections()
        assert sel.tags == []
