import json
import os
from dotenv import load_dotenv

load_dotenv()

with open("config.json", "r") as f:
    config_data = json.load(f)

class Config:
    API_URL = config_data.get("api_url")
    
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

    def __init__(self):
        missing = [
            name for name, value in {
                "API_URL": self.API_URL,
                "ADMIN_USERNAME": self.ADMIN_USERNAME,
                "ADMIN_PASSWORD": self.ADMIN_PASSWORD,
                "JWT_SECRET_KEY": self.JWT_SECRET_KEY,
            }.items() if not value
        ]
        if missing:
            raise ValueError(f"Missing required config variables: {', '.join(missing)}")

settings = Config()