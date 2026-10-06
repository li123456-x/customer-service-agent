import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from tools.order_tool import search_order
from tools.logistics_tool import search_logistics
from tools.refund_tool import search_refund
from tools.knowledge_tool import search_policy_knowledge
from tools.human_review_tool import get_pending_reviews, get_review_detail

mcp = FastMCP("customer-service-agent-mcp")

@mcp.tool()
def query_order(order_no: str) -> dict:
    """根据订单号查询订单信息。"""
    return search_order(order_no)

@mcp.tool()
def query_logistics(order_no: str) -> dict:
    """根据订单号查询物流信息。"""
    return search_logistics(order_no)

@mcp.tool()
def query_refund(order_no: str) -> dict:
    """根据订单号查询退款或售后信息。"""
    return search_refund(order_no)

@mcp.tool()
def search_knowledge(query: str) -> dict:
    """根据用户问题检索企业客服知识库。"""
    return search_policy_knowledge(query)

@mcp.tool()
def list_pending_human_reviews(limit: int = 20) -> dict:
    """查询待人工审核的客服工单。"""
    return get_pending_reviews(limit=limit)

@mcp.tool()
def get_human_review_detail(review_no: str) -> dict:
    """根据审核单号查询人工审核详情。"""
    return get_review_detail(review_no)

if __name__ == "__main__":
    mcp.run()
