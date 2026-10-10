from contextlib import ExitStack, nullcontext
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
import os
from uuid import uuid4
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

with patch.dict(os.environ, {
    "DEEPSEEK_API_KEY": "test-key", "DASHSCOPE_API_KEY": "test-key",
    "POSTGRES_HOST": "localhost", "POSTGRES_DB": "test-db",
    "POSTGRES_USER": "test-user", "POSTGRES_PASSWORD": "test-password",
    "MILVUS_URI": "http://localhost:19530",
}):
    from agent import customer_service_agent
    from api.routes import chat, session, support
    from api.schemas import SupportMessageRequest
    from config.settings import Settings
    from database import chat_repository, human_review_repository, init_db
    from database import live_support_repository as repository
    from database import migrate_live_support as migration
    from graph import nodes
    from tools import live_support_tool as tool


class CustomerDispatchTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(tool, "session_guard", return_value=nullcontext()))
        self.enterContext(patch.object(tool, "create_chat_session_if_not_exists"))
        self.save = self.enterContext(patch.object(tool, "save_chat_message"))
        self.find = self.enterContext(patch.object(tool, "find_chat_session_by_id"))
        self.handoff = self.enterContext(patch.object(tool, "request_handoff"))

    def test_waiting_and_human_messages_never_invoke_ai(self):
        for mode in ("waiting_human", "human"):
            self.find.return_value = {"service_mode": mode}
            ai = Mock()
            result = tool.dispatch_customer_message("message", "s1", ai)
            self.assertIsNone(result["reply"])
            self.assertEqual(result["delivery"], mode)
            ai.assert_not_called()
        self.assertEqual(self.save.call_count, 2)
        self.handoff.assert_not_called()

    def test_explicit_handoff_needs_no_order_and_skips_ai(self):
        self.find.return_value = {"service_mode": "ai"}
        self.handoff.return_value = {"service_mode": "waiting_human"}
        ai = Mock()
        result = tool.dispatch_customer_message("转人工", "s1", ai)
        self.assertEqual(result["delivery"], "waiting_human")
        self.handoff.assert_called_once_with("s1")
        ai.assert_not_called()

    def test_ai_mode_still_calls_original_workflow(self):
        self.find.return_value = {"service_mode": "ai"}
        ai = Mock(return_value="answer")
        result = tool.dispatch_customer_message("物流到哪了", "s1", ai)
        self.assertEqual(result["reply"], "answer")
        ai.assert_called_once_with("物流到哪了", "s1")

    def test_negative_handoff_expression_does_not_transfer(self):
        self.assertFalse(tool.is_handoff_request("不用人工，告诉我发票怎么开"))

    def test_owner_and_generation_are_required(self):
        state = {"service_mode": "human", "assigned_agent": "A", "handoff_version": 2}
        repository.check_owner(state, "A", 2)
        for name, version in (("B", 2), ("A", 1)):
            with self.assertRaises(repository.SupportConflict):
                repository.check_owner(state, name, version)

    def test_empty_staff_message_is_rejected(self):
        with self.assertRaises(ValueError):
            SupportMessageRequest(agent_name="A", handoff_version=1, message="  ", request_id=uuid4())


@unittest.skipUnless(os.getenv("RUN_LIVE_SUPPORT_DB_TESTS") == "1", "Set RUN_LIVE_SUPPORT_DB_TESTS=1 for isolated PostgreSQL tests")
class PostgreSQLSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.rows import dict_row
        from psycopg import sql

        settings = Settings()
        cls.schema = f"test_live_support_{uuid4().hex}"

        def connection(isolated=True):
            return psycopg.connect(
                host=settings.postgres_host, port=settings.postgres_port,
                dbname=settings.postgres_db, user=settings.postgres_user,
                password=settings.postgres_password, row_factory=dict_row,
                connect_timeout=5, options=f"-c search_path={cls.schema}" if isolated else "",
            )

        cls.connection = staticmethod(connection)
        with connection(False) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))

        def cleanup():
            if not cls.schema.startswith("test_live_support_") or len(cls.schema) != 50:
                raise ValueError("Unexpected test schema")
            with connection(False) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

        cls.addClassCleanup(cleanup)
        stack = ExitStack()
        cls.addClassCleanup(stack.close)
        for module in (chat_repository, human_review_repository, repository, migration, init_db):
            stack.enter_context(patch.object(module, "get_connection", side_effect=connection))
        init_db.create_tables()
        migration.migrate_live_support()
        migration.migrate_live_support()
        app = FastAPI()
        for router in (chat.router, session.router, support.router):
            app.include_router(router)
        cls.client = TestClient(app)
        cls.addClassCleanup(cls.client.close)

    def setUp(self):
        self.session_id = f"test-{uuid4()}"

    def request(self):
        response = self.client.post("/handoffs/request", json={"session_id": self.session_id})
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def claim(self, name="A"):
        response = self.client.post(f"/handoffs/{self.session_id}/claim", json={"agent_name": name})
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def test_complete_customer_staff_release_roundtrip(self):
        waiting = self.request()
        self.assertEqual(waiting["service_mode"], "waiting_human")
        with patch.object(customer_service_agent, "_generate_ai_reply") as ai:
            response = self.client.post("/chat", json={"session_id": self.session_id, "message": "补充故障描述"})
            self.assertIsNone(response.json()["data"]["reply"])
            ai.assert_not_called()
        claimed = self.claim()
        payload = {"agent_name": "A", "handoff_version": claimed["handoff_version"],
                   "message": "请上传故障视频", "request_id": str(uuid4())}
        reply_url = f"/handoffs/{self.session_id}/messages"
        first = self.client.post(reply_url, json=payload)
        second = self.client.post(reply_url, json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        messages = self.client.get(f"/sessions/{self.session_id}").json()["data"]["messages"]
        self.assertEqual(sum(m["role"] == "human" for m in messages), 1)
        self.assertEqual(messages[-1]["sender_name"], "A")
        with patch.object(customer_service_agent, "_generate_ai_reply") as ai:
            self.client.post("/chat", json={"session_id": self.session_id, "message": "视频已准备好"})
            ai.assert_not_called()
        response = self.client.post(f"/handoffs/{self.session_id}/release", json={
            "agent_name": "A", "handoff_version": claimed["handoff_version"],
        })
        self.assertEqual(response.json()["data"]["service_mode"], "ai")
        with patch.object(customer_service_agent, "_generate_ai_reply", return_value="AI reply") as ai:
            response = self.client.post("/chat", json={"session_id": self.session_id, "message": "发票怎么开"})
            self.assertEqual(response.json()["data"]["reply"], "AI reply")
            ai.assert_called_once()

    def test_repeated_request_does_not_duplicate_wait_notice(self):
        first = self.request()
        second = self.request()
        self.assertEqual(first["handoff_version"], second["handoff_version"])
        messages = chat_repository.list_messages_by_session_id(self.session_id)
        self.assertEqual(len(messages), 1)

    def test_two_agents_cannot_claim_the_same_session(self):
        self.request()
        def claim(name):
            return self.client.post(f"/handoffs/{self.session_id}/claim", json={"agent_name": name}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, ("A", "B")))
        self.assertEqual(sorted(results), [200, 409])

    def test_stale_generation_and_wrong_agent_are_rejected(self):
        self.request()
        claimed = self.claim()
        path = f"/handoffs/{self.session_id}/messages"
        payload = {"agent_name": "B", "handoff_version": claimed["handoff_version"],
                   "message": "reply", "request_id": str(uuid4())}
        self.assertEqual(self.client.post(path, json=payload).status_code, 409)
        self.client.post(f"/handoffs/{self.session_id}/release", json={
            "agent_name": "A", "handoff_version": claimed["handoff_version"],
        })
        self.request()
        self.claim()
        payload["agent_name"] = "A"
        self.assertEqual(self.client.post(path, json=payload).status_code, 409)

    def test_automatic_review_queues_chat_and_reuses_pending_review(self):
        chat_repository.create_chat_session_if_not_exists(self.session_id)
        state = {"session_id": self.session_id, "order_no": "DD10001",
                 "user_message": "耳机没声音", "context": {}, "review_reason": "质量争议"}
        first = nodes.create_human_review_node(state)
        second = nodes.create_human_review_node(state)
        self.assertEqual(first["trace_steps"][-1]["review_no"], second["trace_steps"][-1]["review_no"])
        self.assertEqual(chat_repository.find_chat_session_by_id(self.session_id)["service_mode"], "waiting_human")

    def test_handoff_waits_for_an_inflight_ai_turn(self):
        entered = Event()
        finish_ai = Event()

        def fake_ai(message, session_id):
            entered.set()
            if not finish_ai.wait(5):
                raise TimeoutError("Test AI gate timed out")
            chat_repository.save_chat_message(session_id, "user", message)
            chat_repository.save_chat_message(session_id, "assistant", "AI answer")
            return "AI answer"

        with patch.object(customer_service_agent, "_generate_ai_reply", side_effect=fake_ai):
            with ThreadPoolExecutor(max_workers=2) as pool:
                ai_request = pool.submit(self.client.post, "/chat", json={
                    "session_id": self.session_id, "message": "物流问题",
                })
                self.assertTrue(entered.wait(5))
                handoff = pool.submit(self.client.post, "/handoffs/request", json={"session_id": self.session_id})
                try:
                    with self.assertRaises(TimeoutError):
                        handoff.result(timeout=0.1)
                finally:
                    finish_ai.set()
                self.assertEqual(ai_request.result(timeout=5).status_code, 200)
                self.assertEqual(handoff.result(timeout=5).json()["data"]["service_mode"], "waiting_human")
        messages = chat_repository.list_messages_by_session_id(self.session_id)
        self.assertEqual([message["role"] for message in messages], ["user", "assistant", "system"])


if __name__ == "__main__":
    unittest.main()
