"""
Pre-flight environment verification script for FORGE.
Validates Python runtime, required packages, and environment configuration.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REQUIRED_PACKAGES = [
    "flask",
    "gunicorn",
    "google.genai",
    "dotenv",
]


def check_python_version():
    current_ver = sys.version_info
    print(f"[OK] Python version: {current_ver.major}.{current_ver.minor}.{current_ver.micro} ({sys.platform})")
    if current_ver.major < 3 or (current_ver.major == 3 and current_ver.minor < 10):
        print("     [WARN] Warning: Python 3.10+ is recommended for optimal compatibility.")
        return False
    return True


def check_dependencies():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            if pkg == "google.genai":
                import google.genai  # noqa: F401
            elif pkg == "dotenv":
                import dotenv  # noqa: F401
            else:
                __import__(pkg)
            print(f"[OK] Package available: {pkg}")
        except ImportError:
            print(f"[FAIL] Missing required package: {pkg}")
            missing.append(pkg)
    return len(missing) == 0


def check_env_configuration():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[FAIL] Environment variable 'GEMINI_API_KEY' is NOT set in environment or .env file.")
        print("       Please copy .env.example to .env and set your GEMINI_API_KEY.")
        return False

    # Never print any part of the key; its length is enough to spot an empty/truncated value.
    print(f"[OK] GEMINI_API_KEY is configured ({len(api_key)} characters)")
    return True


def check_templates():
    template_file = Path(__file__).resolve().parent.parent / "src" / "forge" / "templates" / "index.html"
    if template_file.exists():
        print(f"[OK] UI template found: {template_file.name} ({template_file.stat().st_size:,} bytes)")
        return True
    else:
        print(f"[FAIL] UI template not found at {template_file}")
        return False


def main():
    print("=" * 60)
    print(" FORGE - Environment & System Pre-flight Verification")
    print("=" * 60)

    py_ok = check_python_version()
    dep_ok = check_dependencies()
    tpl_ok = check_templates()
    env_ok = check_env_configuration()

    print("-" * 60)
    if py_ok and dep_ok and tpl_ok and env_ok:
        print(">>> SUCCESS: Environment is ready. You can run 'python app.py'")
        sys.exit(0)
    else:
        print(">>> WARNING/ERROR: One or more pre-flight checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
