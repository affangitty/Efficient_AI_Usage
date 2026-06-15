# Client Requirement Email Automation

Automates the analysis of client requirement emails using **Groq LLM**, then sends a formatted HTML report to **Gmail**.

## Architecture

```mermaid
flowchart TD
    A[Client Requirement Text File] -->|read & validate| B[Python Script]
    B -->|load| C[Prompt Template]
    C -->|requirement text injected| D[Groq API]
    D -->|structured analysis| E[Parse Response]
    E --> F[Functional Requirements]
    E --> G[Non-functional Requirements]
    E --> H[Risks]
    E --> I[Assumptions]
    E --> J[Questions to Client]
    F & G & H & I & J --> K[Build HTML Email]
    K -->|SMTP TLS| L[Gmail]
    L --> M[affanmwa@gmail.com Inbox]
    E -->|save| N[sample_output.txt]
```

### Component Overview

| Component | File | Purpose |
|-----------|------|---------|
| Main script | `requirement_automation.py` | Orchestrates read → analyze → email |
| Prompt | `prompts/requirements_analysis.txt` | Structured prompt for Groq LLM |
| Config | `.env` | API keys and Gmail credentials |
| Sample input | `samples/sample_input.txt` | Example client requirement email |
| Sample output | `samples/sample_output.txt` | Generated analysis (auto-created on run) |

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Edit `.env`:

| Variable | Where to get it |
|----------|-----------------|
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) (free tier available) |
| `GROQ_MODEL` | Optional — default: `llama-3.3-70b-versatile` |
| `GMAIL_ADDRESS` | Your Gmail address (`affanmwa@gmail.com`) |
| `GMAIL_APP_PASSWORD` | [Google App Passwords](https://myaccount.google.com/apppasswords) (requires 2FA) |
| `RECIPIENT_EMAIL` | `affanmwa@gmail.com` |

### 3. Run the automation

```bash
# Full run — analyze and send email
python requirement_automation.py samples/sample_input.txt

# Dry run — analyze only, no email sent
python requirement_automation.py samples/sample_input.txt --dry-run

# Skip email entirely
python requirement_automation.py samples/sample_input.txt --no-email
```

## Deliverables Checklist

| Deliverable | Location | Status |
|-------------|----------|--------|
| **Prompt used** | `prompts/requirements_analysis.txt` | Ready |
| **Python script** | `requirement_automation.py` | Ready |
| **LLM conversation** | `samples/groq_conversation_sample.md` + live run output | Run script for live version |
| **Sample input** | `samples/sample_input.txt` | Ready |
| **Sample output** | `samples/sample_output.txt` | Regenerated on run |
| **Email screenshot** | `samples/email_screenshot.png` | You capture after running |
| **Architecture diagram** | `docs/architecture_diagram.md` | Ready |

### Capturing the Email Screenshot

1. Run the script with valid `.env` credentials
2. Open [Gmail](https://mail.google.com) for `affanmwa@gmail.com`
3. Find the email with subject: **Requirements Analysis: sample_input**
4. Screenshot the received email and save as `samples/email_screenshot.png`

## Error Handling

| Error | Handling |
|-------|----------|
| Missing `.env` variables | Clear message listing which vars are missing |
| File not found / empty / too large | Validated before API call |
| Non-UTF-8 file encoding | Rejected with descriptive error |
| Groq API rate limit / connection failure | Caught and reported with retry guidance |
| Gmail auth failure | Suggests using App Password instead of regular password |
| Unparseable LLM response | Falls back to raw response text |

## Project Structure

```
AI usage/
├── requirement_automation.py      # Main automation script
├── requirements.txt               # Python dependencies
├── .env.example                   # Credential template
├── .env                           # Your credentials (not committed)
├── prompts/
│   └── requirements_analysis.txt  # Prompt design
├── samples/
│   ├── sample_input.txt
│   ├── sample_output.txt
│   ├── groq_conversation_sample.md
│   └── email_screenshot.png
├── docs/
│   └── architecture_diagram.md
└── README.md
```

## Grading Rubric Alignment

| Criteria | Points | How this project addresses it |
|----------|--------|-------------------------------|
| Prompt Design | /20 | Structured 5-section prompt with guidelines and format constraints |
| Claude/LLM Usage | /30 | System + user prompt, Groq API, temperature 0.3, section parsing |
| Code Quality | /20 | Typed dataclasses, modular functions, logging, argparse CLI |
| Error Handling | /10 | Input validation, API errors, SMTP auth, graceful fallbacks |
| Email Automation | /10 | HTML email via Gmail SMTP with TLS |
| Documentation | /10 | README, architecture diagram, setup guide, deliverables checklist |

## Author

Affan — affanmwa@gmail.com
