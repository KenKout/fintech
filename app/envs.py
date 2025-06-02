import os
from dotenv import load_dotenv, find_dotenv

class Settings:
    def __init__(self):
        load_dotenv(find_dotenv())
        self._load_env_variables()

    def _load_env_variables(self):
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        self.OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")


settings = Settings()