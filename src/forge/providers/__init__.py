"""Provider-independent model inference.

Call models through ``ProviderRouter``; provider SDKs and HTTP details stay inside the
adapters (``google_genai``, ``openai_compatible``, ``fake``).
"""
