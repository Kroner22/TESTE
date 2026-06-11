"""Configuration for the CrewAI multi-agent system."""
import os

LLM_MODEL = os.getenv("CREWAI_LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("CREWAI_LLM_TEMPERATURE", "0.3"))
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "")

# When no API key, use a fallback that doesn't require external API
# In production, set OPENAI_API_KEY in .env
FALLBACK_MODE = not bool(LLM_API_KEY)
