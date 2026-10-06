from uuid import uuid4
from agent.customer_service_agent import customer_service_reply

def main():
    session_id = f"session-{uuid4()}"
    print("小想智能客服助手 - LangGraph 后端调试版")
    print("输入 exit / quit / q 退出")
    print("-" * 40)
    while True:
        message = input("用户：").strip()
        if message.lower() in ["exit", "quit", "q"]:
            print("客服：感谢使用，再见。")
            break
        reply = customer_service_reply(
            message=message,
            session_id=session_id,
        )
        print(f"客服：{reply}")

if __name__ == "__main__":
    main()