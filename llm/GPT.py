"""
Use GPT Series Models
"""

from openai import OpenAI
import time
class GPT():
    def __init__(self, model, base_url, api_key):
        self.model_name = model
        self.base_url = base_url
        self.api_key = api_key
        self._endpoint_index = 0

        self._init_model()

    def _init_model(self):
        models = self.model_name if isinstance(self.model_name, list) else [self.model_name]
        base_urls = self.base_url if isinstance(self.base_url, list) else [self.base_url]
        api_keys = self.api_key if isinstance(self.api_key, list) else [self.api_key]

        models = [m for m in (models or []) if m]
        base_urls = [u for u in (base_urls or []) if u]
        api_keys = [k for k in (api_keys or []) if k]
        if not models:
            raise ValueError("model 不能为空")
        if not base_urls:
            raise ValueError("base_url 不能为空")
        if not api_keys:
            raise ValueError("api_key 不能为空")

        triplets: list[tuple[str, str, str]] = []
        if len(models) == 1:
            model = models[0]
            if len(base_urls) == 1 and len(api_keys) >= 1:
                triplets = [(base_urls[0], k, model) for k in api_keys]
            elif len(api_keys) == 1 and len(base_urls) >= 1:
                triplets = [(u, api_keys[0], model) for u in base_urls]
            else:
                if len(base_urls) != len(api_keys):
                    raise ValueError("base_url 与 api_key 列表长度不一致")
                triplets = [(u, k, model) for u, k in zip(base_urls, api_keys, strict=True)]
        else:
            # 支持三元组列表：base_url + api_key + model，按顺序故障切换
            if len(base_urls) == 1 and len(api_keys) == 1:
                triplets = [(base_urls[0], api_keys[0], m) for m in models]
            elif len(base_urls) == 1 and len(api_keys) == len(models):
                triplets = [(base_urls[0], k, m) for k, m in zip(api_keys, models, strict=True)]
            elif len(api_keys) == 1 and len(base_urls) == len(models):
                triplets = [(u, api_keys[0], m) for u, m in zip(base_urls, models, strict=True)]
            else:
                if not (len(base_urls) == len(api_keys) == len(models)):
                    raise ValueError("当 model 为列表时，base_url/api_key/model 需要可广播或三者长度一致")
                triplets = list(zip(base_urls, api_keys, models, strict=True))

        self._endpoints: list[dict] = []
        for url, key, model in triplets:
            self._endpoints.append(
                {
                    "base_url": url,
                    "api_key": key,
                    "model": model,
                    "client": OpenAI(base_url=url, api_key=key),
                }
            )

    def build_prompt(self, question):
        message = []

        message.append(
            {
                "type": "text",
                "text": question,
            }
        )

        prompt =  [
            {
                "role": "user",
                "content": message
            }
        ]
        return prompt

    def call_gpt_eval(self, message, retries=10, wait_time=1, temperature=0.0):
        last_error: Exception | None = None
        for i in range(retries):
            endpoint = self._endpoints[self._endpoint_index]
            client: OpenAI = endpoint["client"]
            model_name = endpoint["model"]
            try:
                result = client.chat.completions.create(
                    model=model_name,
                    messages=message,
                    temperature=temperature,
                )
                response_message = result.choices[0].message.content
                return response_message
            except Exception as e:
                last_error = e
                # 发生错误：按顺序切换到下一个 endpoint
                if len(self._endpoints) > 1:
                    self._endpoint_index = (self._endpoint_index + 1) % len(self._endpoints)
                if i < retries - 1:
                    print(f"Failed to call the API {i+1}/{retries}, switching endpoint and retrying after {wait_time} seconds.")
                    print(e)
                    time.sleep(wait_time)
                    continue
                print(f"Failed to call the API after {retries} attempts.")
                print(e)
                raise
        if last_error is not None:
            raise last_error

    def inference(self, prompt, temperature=0.7):
        prompt = self.build_prompt(prompt)
        response = self.call_gpt_eval(prompt, temperature=temperature)
        return response
    
if __name__ == "__main__":
    # Test OpenAI-compatible endpoint
    model = "gpt-3.5-turbo"
    base_url = "https://api.openai.com/v1"
    api_key = "*"

    gpt = GPT(model, base_url, api_key)
    prompt = "Hello, who are you?"
    response = gpt.inference(prompt, temperature=1)
    print(response)
