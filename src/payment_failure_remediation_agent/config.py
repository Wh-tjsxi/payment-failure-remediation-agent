import os

from dotenv import load_dotenv

load_dotenv()

TASK_QUEUE = "payment-failure-case-queue"

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.environ.get("TEMPORAL_NAMESPACE", "default")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://temporal:temporal@localhost:5432/app"
)

# Sprint 3: real Claude-driven diagnosis. Sonnet only for now -- the
# Haiku/Sonnet cost-split docs/DESIGN.md's tech stack calls for is a
# later cost optimization, not built until real usage volume justifies
# it (docs/DESIGN.md Section 3).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DIAGNOSIS_MODEL = os.environ.get("DIAGNOSIS_MODEL", "claude-sonnet-5")
