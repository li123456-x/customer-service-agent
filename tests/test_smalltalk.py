import os
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {
    "DEEPSEEK_API_KEY": "test-key", "DASHSCOPE_API_KEY": "test-key",
    "POSTGRES_HOST": "localhost", "POSTGRES_DB": "test-db",
    "POSTGRES_USER": "test-user", "POSTGRES_PASSWORD": "test-password",
    "MILVUS_URI": "http://localhost:19530",
}):
    from graph import nodes
    from graph.workflow import customer_service_workflow


class SmalltalkWorkflowTests(unittest.TestCase):
    def test_smalltalk_skips_order_queries_model_and_handoff(self):
        for message in ("你好", "您好！", "在吗？", "谢谢", "好的", "再见", " Hi! "):
            with self.subTest(message=message):
                with (
                    patch.object(nodes, "create_chat_session_if_not_exists"),
                    patch.object(nodes, "save_chat_message") as save_message,
                    patch.object(nodes, "list_recent_messages", return_value=[
                        {"role": "user", "content": "DD10001物流到哪了"},
                    ]),
                    patch.object(nodes, "find_latest_order_no_by_session_id", return_value="DD10001") as restore_order,
                    patch.object(nodes, "save_agent_trace") as save_trace,
                    patch.object(nodes, "search_order") as query_order,
                    patch.object(nodes, "search_logistics") as query_logistics,
                    patch.object(nodes, "search_refund") as query_refund,
                    patch.object(nodes, "search_policy_knowledge") as query_knowledge,
                    patch.object(nodes, "get_model") as model,
                    patch.object(nodes, "create_human_review") as review,
                    patch.object(nodes, "request_handoff") as handoff,
                ):
                    result = customer_service_workflow.invoke({"user_message": message, "session_id": "test-session"})
                self.assertEqual(result["intent"], "smalltalk")
                self.assertEqual(result["final_action"], "smalltalk_reply")
                self.assertIsNone(result["order_no"])
                self.assertFalse(result["need_human_review"])
                for external in (restore_order, query_order, query_logistics, query_refund, query_knowledge, model, review, handoff):
                    external.assert_not_called()
                save_message.assert_any_call("test-session", "assistant", result["final_reply"])
                self.assertEqual(save_trace.call_args.kwargs["final_action"], "smalltalk_reply")
                self.assertEqual([step["node"] for step in result["trace_steps"]], ["start", "parse_message", "smalltalk_reply"])

    def test_greeting_prefix_does_not_hide_a_business_question(self):
        self.assertEqual(nodes.recognize_intent("你好，DD10001物流到哪了")[0], "logistics_query")
        self.assertEqual(nodes.recognize_intent("谢谢，发票怎么开")[0], "knowledge_query")
        self.assertEqual(nodes.recognize_intent("你好，耳机没声音，我要退款")[0], "after_sale_refund")


if __name__ == "__main__":
    unittest.main()
