import os
from dotenv import load_dotenv

load_dotenv()

# ── Model pricing ────────────────────────────────────────────────────────────
OPENAI_INPUT_PRICE       = 0.15  / 1_000_000
OPENAI_OUTPUT_PRICE      = 0.60  / 1_000_000

CLAUDE_INPUT_PRICE       = 0.80  / 1_000_000
CLAUDE_OUTPUT_PRICE      = 4.00  / 1_000_000
CLAUDE_CACHE_WRITE_PRICE = 1.00  / 1_000_000
CLAUDE_CACHE_READ_PRICE  = 0.08  / 1_000_000

# ── Inventory parameters ──────────────────────────────────────────────────────
LEAD_TIME_MONTHS = 3
Z_SCORE          = 1.645   # 95% service level

# ── Agent loop limits ─────────────────────────────────────────────────────────
MAX_AGENT_ITERATIONS = 5
MAX_TOOL_PAIRS       = 4   # tool-call/result pairs kept in Claude context
CLAUDE_MODEL         = "claude-haiku-4-5-20251001"

# ── Databricks ────────────────────────────────────────────────────────────────
DATABRICKS_HOST      = os.getenv("DATABRICKS_HOST")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")
DATABRICKS_TOKEN     = os.getenv("DATABRICKS_TOKEN")

# ── API keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
COHERE_API_KEY    = os.getenv("COHERE_API_KEY")   # optional — enables rerank RAG
GROQ_API_KEY      = os.getenv("GROQ_API_KEY")     # optional — enables Llama intent router
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY")   # optional — enables Gemini Flash bulk analyst

# ── App auth (optional — leave blank in .env to disable) ─────────────────────
APP_USERNAME = os.getenv("APP_USERNAME")
APP_PASSWORD = os.getenv("APP_PASSWORD")

# ── Startup validation ────────────────────────────────────────────────────────
_REQUIRED = {"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY, "OPENAI_API_KEY": OPENAI_API_KEY}
_missing  = [k for k, v in _REQUIRED.items() if not v]
if _missing:
    raise EnvironmentError(f"Missing required env vars: {', '.join(_missing)}. Check your .env file.")


def calculate_cost(input_tokens, output_tokens, input_price, output_price):
    return (input_tokens * input_price) + (output_tokens * output_price)
