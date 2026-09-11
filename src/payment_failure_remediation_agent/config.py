import os

from dotenv import load_dotenv

load_dotenv()

TASK_QUEUE = "payment-failure-case-queue"

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://temporal:temporal@localhost:5432/app"
)
