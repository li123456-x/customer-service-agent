import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError


# Import configuration with dummy credentials; every external call is mocked.
with patch.dict(os.environ, {
    "DEEPSEEK_API_KEY": "test-key",
    "DASHSCOPE_API_KEY": "test-key",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_DB": "test-db",
    "POSTGRES_USER": "test-user",
    "POSTGRES_PASSWORD": "test-password",
    "MILVUS_URI": "http://localhost:19530",
    "RAG_TOP_K": "5",
    "RAG_MIN_RELEVANCE_SCORE": "0.55",
}):
    from graph import nodes
    from graph.workflow import customer_service_workflow
    from rag import retriever
    from tools import knowledge_tool
    from api.routes.knowledge import router as knowledge_router
    from config.settings import Settings


def hit(score, text="policy"):
    return {
        "distance": score,
        "entity": {"text": text, "source": "policy.txt", "path": "data/policy.txt"},
    }


class RelevanceFilterTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.has_collection.return_value = True
        self.embeddings = Mock()
        self.embeddings.embed_query.return_value = [0.1, 0.2]
        self.enterContext(patch.object(retriever, "MilvusClient", return_value=self.client))
        self.enterContext(patch.object(retriever, "get_embeddings", return_value=self.embeddings))
        self.enterContext(patch.object(retriever, "get_milvus_config", return_value={
            "uri": "http://localhost:19530", "db_name": "test-db", "collection_name": "docs",
        }))
        self.enterContext(patch.object(retriever.settings, "rag_top_k", 5))
        self.enterContext(patch.object(retriever.settings, "rag_min_relevance_score", 0.55))

    def test_preserves_order_and_keeps_threshold_boundary(self):
        self.client.search.return_value = [[hit(0.82, "first"), hit(0.55, "second"), hit(0.54)]]
        documents = retriever.search_knowledge("question")
        self.assertEqual([item["score"] for item in documents], [0.82, 0.55])
        self.assertEqual([item["text"] for item in documents], ["first", "second"])
        self.assertEqual(documents[0]["source"], "policy.txt")
        self.assertEqual(self.client.search.call_args.kwargs["limit"], 5)

    def test_all_low_scores_return_no_documents(self):
        self.client.search.return_value = [[hit(0.54), hit(0.2), hit(-0.1)]]
        self.assertEqual(retriever.search_knowledge("question"), [])

    def test_missing_and_nan_scores_are_not_evidence(self):
        self.client.search.return_value = [[hit(None), hit(float("nan")), hit(0.6)]]
        self.assertEqual([item["score"] for item in retriever.search_knowledge("question")], [0.6])

    def test_reads_configured_threshold_and_preserves_explicit_k(self):
        self.client.search.return_value = [[hit(0.7), hit(0.6)]]
        with patch.object(retriever.settings, "rag_min_relevance_score", 0.7):
            self.assertEqual(len(retriever.search_knowledge("question", top_k=3)), 1)
        self.assertEqual(self.client.search.call_args.kwargs["limit"], 3)

    def test_default_k_reads_configuration_instead_of_a_hardcoded_value(self):
        self.client.search.return_value = [[hit(0.6)]]
        with patch.object(retriever.settings, "rag_top_k", 8):
            retriever.search_knowledge("question")
        self.assertEqual(self.client.search.call_args.kwargs["limit"], 8)

    def test_invalid_explicit_k_is_rejected_before_embedding(self):
        for k in (0, -1, 101, True, 3.5):
            with self.subTest(k=k), self.assertRaises(ValueError):
                retriever.search_knowledge("question", top_k=k)
        self.embeddings.embed_query.assert_not_called()

    def test_admin_api_uses_backend_default_and_threshold(self):
        self.client.search.return_value = [[hit(0.6), hit(0.54)]]
        app = FastAPI()
        app.include_router(knowledge_router)
        with TestClient(app) as browser:
            response = browser.get("/knowledge/search", params={"query": "question"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["data"]), 1)
        self.assertEqual(self.client.search.call_args.kwargs["limit"], 5)

    def test_admin_api_preserves_explicit_k(self):
        self.client.search.return_value = [[hit(0.6)]]
        app = FastAPI()
        app.include_router(knowledge_router)
        with TestClient(app) as browser:
            response = browser.get("/knowledge/search", params={"query": "question", "top_k": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.search.call_args.kwargs["limit"], 3)

    def test_admin_api_rejects_out_of_range_k(self):
        app = FastAPI()
        app.include_router(knowledge_router)
        with TestClient(app) as browser:
            for k in (0, -1, 101):
                with self.subTest(k=k):
                    response = browser.get("/knowledge/search", params={"query": "question", "top_k": k})
                    self.assertEqual(response.status_code, 422)
        self.embeddings.embed_query.assert_not_called()

    def test_empty_search_results_return_no_documents(self):
        for results in ([], [[]]):
            with self.subTest(results=results):
                self.client.search.return_value = results
                self.assertEqual(retriever.search_knowledge("question"), [])

    def test_absent_collection_returns_no_documents(self):
        self.client.has_collection.return_value = False
        self.assertEqual(retriever.search_knowledge("question"), [])
        self.client.search.assert_not_called()

    def test_service_exception_is_not_disguised_as_missing_knowledge(self):
        self.client.search.side_effect = RuntimeError("service unavailable")
        with self.assertRaisesRegex(RuntimeError, "service unavailable"):
            retriever.search_knowledge("question")


class KnowledgeReplyTests(unittest.TestCase):
    def test_tool_reports_insufficient_evidence(self):
        with patch.object(knowledge_tool, "search_knowledge", return_value=[]):
            result = knowledge_tool.search_policy_knowledge("question")
        self.assertFalse(result["success"])
        self.assertEqual(result["data"], [])

    def test_no_evidence_does_not_invoke_model_even_with_an_order(self):
        for order_result in ({"success": False, "message": "no order"},
                             {"success": True, "data": {"order_no": "DD10001"}}):
            with self.subTest(order_result=order_result), patch.object(nodes, "get_model") as model:
                result = nodes.generate_reply_node({
                    "intent": "knowledge_query", "order_result": order_result,
                    "knowledge_result": {"success": False, "data": []}, "trace_steps": [],
                })
            model.assert_not_called()
            self.assertEqual(result["final_action"], "knowledge_not_found")
            self.assertEqual(result["trace_steps"][-1]["final_action"], "knowledge_not_found")

    def test_sufficient_evidence_keeps_model_reply_path(self):
        model = Mock()
        model.invoke.return_value = SimpleNamespace(content="grounded answer")
        with patch.object(nodes, "get_model", return_value=model):
            result = nodes.generate_reply_node({
                "intent": "knowledge_query", "user_message": "question",
                "order_result": {"success": False, "message": "no order"},
                "knowledge_result": {"success": True, "data": [{"text": "policy"}]},
                "context": {},
            })
        model.invoke.assert_called_once()
        self.assertEqual(result["final_action"], "auto_reply")
        self.assertEqual(result["final_reply"], "grounded answer")

    def test_missing_policy_does_not_block_business_facts(self):
        model = Mock()
        model.invoke.return_value = SimpleNamespace(content="verified logistics")
        with patch.object(nodes, "get_model", return_value=model):
            result = nodes.generate_reply_node({
                "intent": "logistics_query", "user_message": "question",
                "order_result": {"success": True, "data": {"order_no": "DD10001"}},
                "knowledge_result": {"success": False, "data": []}, "context": {},
            })
        model.invoke.assert_called_once()
        self.assertEqual(result["final_action"], "auto_reply")

    def test_missing_order_keeps_existing_reply(self):
        with patch.object(nodes, "get_model") as model:
            result = nodes.generate_reply_node({
                "intent": "order_query", "order_result": {"success": False, "message": "no order"},
                "knowledge_result": {"success": False, "data": []},
            })
        model.assert_not_called()
        self.assertEqual(result["final_action"], "order_not_found")
        self.assertEqual(result["final_reply"], "no order")

    def test_workflow_saves_no_evidence_reply_and_trace(self):
        with (
            patch.object(nodes, "create_chat_session_if_not_exists"),
            patch.object(nodes, "save_chat_message") as save_message,
            patch.object(nodes, "list_recent_messages", return_value=[]),
            patch.object(nodes, "find_latest_order_no_by_session_id", return_value=None),
            patch.object(nodes, "search_policy_knowledge", return_value={
                "success": False, "message": "insufficient evidence", "data": [],
            }),
            patch.object(nodes, "save_agent_trace") as save_trace,
            patch.object(nodes, "get_model") as model,
            patch.object(nodes, "create_human_review") as create_review,
        ):
            result = customer_service_workflow.invoke({
                "user_message": "\u53d1\u7968\u600e\u4e48\u5f00", "session_id": "test-session",
            })
        self.assertEqual(result["final_action"], "knowledge_not_found")
        model.assert_not_called()
        create_review.assert_not_called()
        save_message.assert_any_call("test-session", "assistant", result["final_reply"])
        self.assertEqual(save_trace.call_args.kwargs["final_action"], "knowledge_not_found")
        self.assertEqual([step["node"] for step in result["trace_steps"]], [
            "start", "parse_message", "query_knowledge", "knowledge_only_context", "generate_reply",
        ])


class RagConfigurationTests(unittest.TestCase):
    def settings(self, **overrides):
        values = {
            "deepseek_api_key": "test-key", "dashscope_api_key": "test-key",
            "postgres_host": "localhost", "postgres_db": "test-db",
            "postgres_user": "test-user", "postgres_password": "test-password",
            "milvus_uri": "http://localhost:19530", **overrides,
        }
        with patch.dict(os.environ, {}, clear=True):
            return Settings(_env_file=None, **values)

    def test_new_defaults_without_dotenv(self):
        settings = self.settings()
        self.assertEqual(settings.rag_top_k, 5)
        self.assertEqual(settings.rag_min_relevance_score, 0.55)

    def test_invalid_configuration_is_rejected(self):
        for values in ({"rag_top_k": 0}, {"rag_top_k": 101},
                       {"rag_min_relevance_score": -1.1}, {"rag_min_relevance_score": 1.1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.settings(**values)


if __name__ == "__main__":
    unittest.main()
