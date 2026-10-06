from langchain.chat_models import init_chat_model
from config.settings import settings

def get_model():
    if not settings.deepseek_api_key:
        raise RuntimeError("缺少必要环境变量：DEEPSEEK_API_KEY")

    return init_chat_model(
        model="deepseek-v4-flash",
        model_provider="deepseek",
        extra_body={
            "thinking": {
                "type": "disabled",
            }
        },
    )