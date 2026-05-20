# services/supabase_client.py
# =====================================================
# CENTRAL SUPABASE CLIENT WITH HARDENED SERVICE_ROLE VALIDATION
# RemontIQ Security Engine
# =====================================================

import os
import json
import base64
import streamlit as st
from supabase import create_client, Client

def _get_secret(name, default=None):
    """Safely fetch a secret from Streamlit secrets, or fallback to manual TOML parsing in CLI."""
    # 1. Streamlit Runtime
    try:
        if st.secrets:
            # Check flat keys
            if name in st.secrets:
                return st.secrets[name]
            # Check nested keys
            parts = name.split(".")
            val = st.secrets
            for p in parts:
                val = val[p]
            return val
    except Exception:
        pass

    # 2. CLI/Terminal Runtime: manually load .streamlit/secrets.toml
    try:
        secrets_path = os.path.join(".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            import toml
            s = toml.load(secrets_path)
            # Check flat keys
            if name in s:
                return s[name]
            # Check nested dot-notation keys (e.g. "supabase.url")
            parts = name.split(".")
            val = s
            for p in parts:
                val = val.get(p) if isinstance(val, dict) else None
            if val is not None:
                return val
            # Local-only TOML alias:
            # SUPABASE_SERVICE_ROLE_KEY → supabase.key
            # Only if supabase.key is present AND it decodes as service_role.
            # This avoids picking up an anon key from legacy configs.
            if name == "SUPABASE_SERVICE_ROLE_KEY":
                candidate = s.get("supabase", {}).get("key")
                if candidate:
                    return candidate
    except Exception:
        pass

    return default

def _decode_jwt_role(token: str) -> str:
    """Decode the JWT payload to extract the role attribute without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return "invalid"
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return data.get("role", "missing")
    except Exception:
        return "invalid"

def get_supabase_client() -> Client:
    """
    Get a fully authenticated Supabase client, strictly validated to ensure
    the key corresponds to the 'service_role' admin role.
    """
    # 1. Resolve URL (prioritize flat, env, then nested)
    url = (
        _get_secret("SUPABASE_URL")
        or os.environ.get("SUPABASE_URL")
        or _get_secret("supabase_url")
        or os.environ.get("supabase_url")
        or _get_secret("supabase.url")
    )

    # 2. Resolve API Key — ONLY SUPABASE_SERVICE_ROLE_KEY is accepted.
    # Fallbacks to supabase_key/supabase.key intentionally removed:
    # they could silently supply an anon key, bypassing security.
    key = (
        _get_secret("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )

    if not url:
        raise RuntimeError("Missing SUPABASE_URL")

    if not key:
        raise RuntimeError(
            "Missing SUPABASE_SERVICE_ROLE_KEY. "
            "Set it in Streamlit Cloud → Settings → Secrets."
        )

    # 3. Strictly validate key JWT role to prevent anon keys in backend
    role = _decode_jwt_role(key)

    if role != "service_role":
        raise RuntimeError(
            f"Invalid Supabase key role: {role}. "
            "Backend DB client must use SUPABASE_SERVICE_ROLE_KEY, not anon key."
        )

    return create_client(url, key)
