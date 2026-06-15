"""
Requirement Email Automation
----------------------------
Reads a client requirement text file, uses Groq LLM to generate structured
requirements analysis, formats an HTML email, and sends it via Gmail SMTP.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import smtplib
import sys
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from groq import APIConnectionError, APIError, Groq, RateLimitError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "llama-3.3-70b-versatile"
PROMPT_FILE = Path(__file__).parent / "prompts" / "requirements_analysis.txt"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
MAX_FILE_SIZE_BYTES = 512_000  # 500 KB


@dataclass
class Config:
    groq_api_key: str
    gmail_address: str
    gmail_app_password: str
    recipient_email: str
    model: str = DEFAULT_MODEL


@dataclass
class AnalysisResult:
    functional_requirements: str
    non_functional_requirements: str
    risks: str
    assumptions: str
    questions_to_client: str
    raw_response: str


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
def load_config() -> Config:
    """Load and validate environment configuration."""
    load_dotenv()

    missing: list[str] = []
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
    gmail_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    recipient = os.getenv("RECIPIENT_EMAIL", "").strip()

    if not api_key or api_key == "your_groq_api_key_here":
        missing.append("GROQ_API_KEY")
    if not gmail_address:
        missing.append("GMAIL_ADDRESS")
    if not gmail_password or gmail_password == "your_16_char_app_password":
        missing.append("GMAIL_APP_PASSWORD")
    if not recipient:
        missing.append("RECIPIENT_EMAIL")

    if missing:
        raise EnvironmentError(
            f"Missing or placeholder environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in your credentials."
        )

    return Config(
        groq_api_key=api_key,
        gmail_address=gmail_address,
        gmail_app_password=gmail_password,
        recipient_email=recipient,
        model=model,
    )


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------
def read_requirement_file(file_path: Path) -> str:
    """Read and validate the client requirement text file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Requirement file not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    size = file_path.stat().st_size
    if size == 0:
        raise ValueError(f"Requirement file is empty: {file_path}")
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"Requirement file too large ({size} bytes). "
            f"Maximum allowed: {MAX_FILE_SIZE_BYTES} bytes."
        )

    try:
        text = file_path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Requirement file must be UTF-8 encoded: {file_path}"
        ) from exc

    if not text:
        raise ValueError(f"Requirement file contains no readable text: {file_path}")

    logger.info("Read requirement file: %s (%d characters)", file_path, len(text))
    return text


def load_prompt_template(prompt_path: Path = PROMPT_FILE) -> str:
    """Load the LLM prompt template from disk."""
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Groq LLM integration
# ---------------------------------------------------------------------------
def build_user_message(requirement_text: str, prompt_template: str) -> str:
    """Inject requirement text into the prompt template."""
    return prompt_template.replace("{{REQUIREMENT_TEXT}}", requirement_text)


def _extract_section(text: str, section_name: str) -> str:
    """Extract a numbered section from the LLM structured response."""
    pattern = (
        rf"(?:^|\n)\s*\d+\.\s*{re.escape(section_name)}\s*\n"
        rf"(.*?)(?=\n\s*\d+\.\s|\Z)"
    )
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def parse_llm_response(response_text: str) -> AnalysisResult:
    """Parse the LLM structured response into sections."""
    sections = {
        "functional_requirements": _extract_section(
            response_text, "Functional Requirements"
        ),
        "non_functional_requirements": _extract_section(
            response_text, "Non-functional Requirements"
        ),
        "risks": _extract_section(response_text, "Risks"),
        "assumptions": _extract_section(response_text, "Assumptions"),
        "questions_to_client": _extract_section(
            response_text, "Questions to Client"
        ),
    }

    # Fallback: if parsing fails, put everything in functional requirements
    if not any(sections.values()):
        logger.warning(
            "Could not parse structured sections from LLM response; "
            "using raw response as fallback."
        )
        sections["functional_requirements"] = response_text

    return AnalysisResult(raw_response=response_text, **sections)


def call_groq(
    client: Groq,
    requirement_text: str,
    prompt_template: str,
    model: str,
) -> AnalysisResult:
    """Send requirement text to Groq and return parsed analysis."""
    user_message = build_user_message(requirement_text, prompt_template)

    logger.info("Calling Groq API (model: %s)...", model)
    try:
        completion = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior business analyst. Analyze client "
                        "requirement emails and produce clear, actionable "
                        "documentation. Always follow the exact output format "
                        "requested."
                    ),
                },
                {"role": "user", "content": user_message},
            ],
        )
    except RateLimitError as exc:
        raise RuntimeError(
            "Groq API rate limit exceeded. Wait a moment and retry."
        ) from exc
    except APIConnectionError as exc:
        raise RuntimeError(
            "Could not connect to Groq API. Check your internet connection."
        ) from exc
    except APIError as exc:
        raise RuntimeError(f"Groq API error: {exc}") from exc

    if not completion.choices:
        raise RuntimeError("Groq returned an empty response.")

    response_text = completion.choices[0].message.content or ""
    if not response_text.strip():
        raise RuntimeError("Groq returned an empty response.")

    logger.info("Groq response received (%d characters).", len(response_text))
    return parse_llm_response(response_text)


# ---------------------------------------------------------------------------
# Email formatting & sending
# ---------------------------------------------------------------------------
def _format_section_html(title: str, content: str) -> str:
    """Convert bullet-point text to an HTML section."""
    if not content.strip():
        content = "<em>No items identified.</em>"
    else:
        lines = [
            line.strip().lstrip("-•*").strip()
            for line in content.splitlines()
            if line.strip()
        ]
        if lines:
            items = "".join(f"<li>{line}</li>" for line in lines)
            content = f"<ul>{items}</ul>"
        else:
            content = f"<p>{content}</p>"

    return f"""
    <div style="margin-bottom: 24px;">
        <h2 style="color: #1a365d; border-bottom: 2px solid #3182ce;
                   padding-bottom: 6px;">{title}</h2>
        {content}
    </div>
    """


def build_html_email(
    analysis: AnalysisResult,
    source_filename: str,
    requirement_preview: str,
) -> str:
    """Build a formatted HTML email body from the analysis."""
    preview = requirement_preview[:500]
    if len(requirement_preview) > 500:
        preview += "..."

    sections_html = "".join(
        [
            _format_section_html("Functional Requirements", analysis.functional_requirements),
            _format_section_html(
                "Non-functional Requirements", analysis.non_functional_requirements
            ),
            _format_section_html("Risks", analysis.risks),
            _format_section_html("Assumptions", analysis.assumptions),
            _format_section_html("Questions to Client", analysis.questions_to_client),
        ]
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #2d3748;
             max-width: 800px; margin: 0 auto; padding: 20px;">
    <div style="background: #1a365d; color: white; padding: 20px;
                border-radius: 8px 8px 0 0;">
        <h1 style="margin: 0;">Requirements Analysis Report</h1>
        <p style="margin: 8px 0 0; opacity: 0.9;">Generated by Groq AI Automation</p>
    </div>
    <div style="background: #f7fafc; padding: 20px; border: 1px solid #e2e8f0;">
        <p><strong>Source File:</strong> {source_filename}</p>
        <p><strong>Original Requirement (preview):</strong></p>
        <blockquote style="background: white; padding: 12px; border-left: 4px solid
                           #3182ce; margin: 0; font-style: italic;">
            {preview}
        </blockquote>
    </div>
    <div style="padding: 20px; border: 1px solid #e2e8f0; border-top: none;">
        {sections_html}
    </div>
    <div style="background: #edf2f7; padding: 12px 20px; text-align: center;
                font-size: 12px; color: #718096; border-radius: 0 0 8px 8px;">
        This email was automatically generated from a client requirement file.
    </div>
</body>
</html>"""


def send_email(
    config: Config,
    subject: str,
    html_body: str,
    dry_run: bool = False,
) -> None:
    """Send the formatted email via Gmail SMTP."""
    if dry_run:
        logger.info("[DRY RUN] Email would be sent to: %s", config.recipient_email)
        logger.info("[DRY RUN] Subject: %s", subject)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.gmail_address
    msg["To"] = config.recipient_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    logger.info("Sending email to %s via Gmail SMTP...", config.recipient_email)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config.gmail_address, config.gmail_app_password)
            server.sendmail(
                config.gmail_address,
                config.recipient_email,
                msg.as_string(),
            )
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            "Gmail authentication failed. Verify GMAIL_ADDRESS and "
            "GMAIL_APP_PASSWORD (use a Google App Password, not your "
            "regular account password)."
        ) from exc
    except smtplib.SMTPException as exc:
        raise RuntimeError(f"Failed to send email: {exc}") from exc

    logger.info("Email sent successfully to %s", config.recipient_email)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def save_analysis_output(
    analysis: AnalysisResult,
    output_path: Path,
) -> None:
    """Save the LLM analysis to a text file for submission."""
    content = f"""REQUIREMENTS ANALYSIS OUTPUT
{'=' * 60}

1. Functional Requirements
{analysis.functional_requirements or 'N/A'}

2. Non-functional Requirements
{analysis.non_functional_requirements or 'N/A'}

3. Risks
{analysis.risks or 'N/A'}

4. Assumptions
{analysis.assumptions or 'N/A'}

5. Questions to Client
{analysis.questions_to_client or 'N/A'}

{'=' * 60}
RAW GROQ RESPONSE
{'=' * 60}
{analysis.raw_response}
"""
    output_path.write_text(content, encoding="utf-8")
    logger.info("Analysis saved to: %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze client requirements with Groq and email the report."
    )
    parser.add_argument(
        "requirement_file",
        type=Path,
        help="Path to the client requirement text file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Save analysis output to this file (default: samples/sample_output.txt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate analysis and email HTML but do not send email",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip email sending entirely (still saves output)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        config = load_config()
        requirement_text = read_requirement_file(args.requirement_file)
        prompt_template = load_prompt_template()

        client = Groq(api_key=config.groq_api_key)
        analysis = call_groq(
            client, requirement_text, prompt_template, config.model
        )

        # Save output
        output_path = args.output or (
            Path(__file__).parent / "samples" / "sample_output.txt"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_analysis_output(analysis, output_path)

        # Build and send email
        if not args.no_email:
            subject = (
                f"Requirements Analysis: {args.requirement_file.stem}"
            )
            html_body = build_html_email(
                analysis,
                args.requirement_file.name,
                requirement_text,
            )
            send_email(config, subject, html_body, dry_run=args.dry_run)

        logger.info("Done.")
        return 0

    except (EnvironmentError, FileNotFoundError, ValueError) as exc:
        logger.error("Configuration/input error: %s", exc)
        return 1
    except RuntimeError as exc:
        logger.error("Runtime error: %s", exc)
        return 2
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        return 3


if __name__ == "__main__":
    sys.exit(main())
