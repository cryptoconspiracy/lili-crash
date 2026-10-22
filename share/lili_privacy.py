"""Best-effort initial-context redaction; this is not a filter for agent tool output."""
import re


def redact(text):
    text = re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
                  "[REDACTED PRIVATE KEY]", text, flags=re.S)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+\S+", r"\1[REDACTED]", text)
    text = re.sub(r'''(?i)(["']?(?:password|passwd|token|api[_-]?key|secret|access[_-]?key|cookie)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)''',
                  r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b", "[REDACTED KEY]", text)
    text = re.sub(r"(https?://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", text)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]", text)
    return text


def remote_notice(agent, endpoint="", translate=lambda text: text):
    destination = agent + (" (" + endpoint + ")" if endpoint else "")
    return translate("This session uses {destination}. Logs and command output read by this AI may leave this computer "
            "and contain passwords, tokens or private documents.\n\n"
            "Lili masks common secrets in the initial context only. It cannot filter additional output read by the agent "
            "or guarantee that all sensitive data is removed.\n\n"
            "Use Ollama on localhost to keep the diagnosis on this computer. Continue with this session?").format(destination=destination)
