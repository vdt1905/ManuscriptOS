"""
FormatForge AI — Configuration
Loads settings from .env file and provides typed config.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ----- Paths -----
PROJECT_ROOT = Path(__file__).resolve().parent.parent      # backend_ai/
PACKAGE_DIR = Path(__file__).resolve().parent               # backend_ai/deepscan/
STYLES_DIR = PACKAGE_DIR / "styles"
# Same folder routes.py serves downloads from (and .gitignore excludes).
OUTPUT_DIR = PACKAGE_DIR / "output"
OUTPUT_FORMATTED_DIR = OUTPUT_DIR / "formatted"
OUTPUT_REPORTS_DIR = OUTPUT_DIR / "reports"

# Ensure output directories exist
OUTPUT_FORMATTED_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ----- Environment -----
load_dotenv(PROJECT_ROOT / ".env")

# LLM settings
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# Server settings
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ----- Application Constants -----
APP_NAME = "FormatForge AI"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Agentic Manuscript Formatting System — Agent Paperpal"

# Default style
DEFAULT_STYLE = "apa7"

# Supported input formats
SUPPORTED_INPUT_FORMATS = [".docx", ".pdf", ".txt"]

# Available hardcoded styles
AVAILABLE_STYLES = {
    "apa7": "APA 7th Edition",
    "vancouver": "Vancouver",
    "ieee": "IEEE",
    "mla": "MLA 9th Edition",
    "chicago": "Chicago 17th Edition",
}
