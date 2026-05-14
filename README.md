# Telecom AI Operations Assistant (AWS Bedrock)

An AI-powered operations assistant for telecom NOC/SOC/Field Engineering teams, built using **AWS Bedrock**, **FastAPI**, and **Streamlit**. The assistant performs Retrieval-Augmented Generation (RAG) over a 3GPP telecom incident dataset and curated supplemental knowledge to help diagnose incidents, identify root causes, and recommend recovery actions.

> Built during a hackathon using the [Cursor Agent Toolkit for AWS](https://github.com/aws/cursor-agent-toolkit-for-aws) to scaffold infrastructure, establish AWS Bedrock connectivity, and accelerate development.

---

## What It Does

- Answers telecom incident, alarm, and Root Cause Analysis (RCA) questions using natural language
- Retrieves relevant context from a **3GPP standard telecom dataset** (1000+ incidents across 5G Core, LTE/RAN, IMS/VoLTE, Transport, Fiber, OSS/BSS)
- Augments answers with curated **supplemental telecom knowledge** (RCA playbooks, KPI cheatsheets, alarm guides, support principles)
- Maintains **short-term memory** (per session) for conversational continuity
- Maintains **long-term memory** (per user, across sessions) for preferences, domain interests, and recurring topics
- Provides a **severity dashboard** with real-time incident counts (Critical/High/Medium/Low)
- Supports **incident ID search** (full or partial match) from the sidebar
- User Tracker function to add/modify status of any incident ID
- Exposes a RESTful **FastAPI backend** and a friendly **Streamlit chat UI**

---

## Architecture

```text
+---------------------+        +---------------------+        +---------------------+
|   Streamlit UI      | -----> |   FastAPI Backend    | -----> |   AWS Bedrock       |
|   (Chat + Dashboard)|  HTTP  |   (RAG + Memory)    | boto3  |   (Converse API)    |
+---------------------+        +---------------------+        +---------------------+
                                       |
                          +------------+------------+
                          |            |            |
                    3GPP Dataset  Supplemental  Memory Store
                     (.xlsx)     Knowledge     (JSON files)
                                  (.txt)
```

### How It Works

1. **User submits a query** via the Streamlit chat interface
2. **Retrieval** - The backend scores dataset rows and supplemental docs against the query using a weighted TF-IDF-like scorer with telecom-specific boosting (domain, issue type, severity, telecom keywords like 5G, VoLTE, SCTP, etc.)
3. **Context assembly** - Top-K dataset hits + supplemental matches are assembled alongside short-term (session) and long-term (user) memory
4. **Prompt construction** - A structured prompt is built with system instructions, memory blocks, retrieved context, and the user query
5. **Bedrock invocation** - The prompt is sent to AWS Bedrock via the **Converse API** (with InvokeModel as fallback) using boto3
6. **Response + memory update** - The structured answer is returned, and both memory stores are updated

---

## How We Used AWS Bedrock

### Connection Setup

- **boto3 client** - A `bedrock-runtime` client is initialized with the configured AWS region
- **Converse API** (primary) - Uses `bedrock_runtime.converse()` with structured `system` and `messages` parameters, the recommended API for multi-turn conversations
- **InvokeModel API** (fallback) - Falls back to `bedrock_runtime.invoke_model()` with raw JSON payload if Converse fails
- **Model** - Defaults to `us.amazon.nova-lite-v1:0` (configurable via `BEDROCK_MODEL_ID` env var); also tested with `anthropic.claude-3-haiku-20240307-v1:0`
- **IAM permissions** - EC2 instance role grants `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`

### Inference Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `maxTokens` | 900 | Tuned for structured telecom responses |
| `temperature` | 0.3 | Low creativity, high precision for operational answers |
| `topP` | 0.9 | Balanced nucleus sampling |

---

## How We Used the Cursor Agent Toolkit for AWS

The Agent Toolkit for AWS was used throughout development to:

1. **Scaffold the project** - Generated the initial FastAPI + Streamlit project structure with proper Python packaging
2. **AWS Bedrock integration** - Used the toolkit's AWS skill guidance to correctly configure the boto3 Bedrock client, choose between Converse and InvokeModel APIs, and set up IAM permissions
3. **CloudFormation infrastructure** - Generated the `infra/telecom-stack.yaml` CloudFormation template for EC2 deployment with:
   - IAM roles with least-privilege Bedrock and S3 permissions
   - Instance profile for secure credential management (no hardcoded keys)
   - Security groups for Streamlit (8501) and FastAPI (8000)
   - UserData bootstrap script with systemd services
   - SSM Session Manager for secure SSH-less access
4. **Iterative development** - The agent toolkit helped debug Bedrock API responses, refine prompt engineering, and implement the dual-memory architecture

---

## Folder Structure

telecom-ai-assistant-bedrock/
├── backend/
│   ├── app.py                  # FastAPI routes (chat, health, memory, search)
│   ├── bedrock_client.py       # AWS Bedrock Converse + InvokeModel client
│   ├── config.py               # Environment-driven configuration
│   ├── dataset_loader.py       # 3GPP dataset loader + weighted retrieval engine
│   ├── memory_store.py         # Short-term + long-term memory (JSON persistence)
│   └── prompt_builder.py       # System prompt + structured user prompt builder
├── frontend/
│   └── streamlit_app.py        # Chat UI, severity dashboard, incident search
├── data/
│   ├── 3gpp_standard_telecom_dataset_updated.xlsx
│   ├── memory/                 # Auto-created: session + long-term memory JSONs
│   └── supplemental/           # Curated telecom knowledge files
│       ├── telecom_alarm_playbook.txt
│       ├── telecom_kpi_cheatsheet.txt
│       ├── telecom_rca_playbook.txt
│       └── telecom_support_principles.txt
├── infra/
│   └── telecom-stack.yaml      # CloudFormation template for EC2 deployment
├── .env.example                # Sample environment variables
├── .gitignore
├── LICENSE
├── requirements.txt            # Python dependencies
└── README.md

---

## Setup

### Prerequisites

- Python 3.11+
- An AWS account with Amazon Bedrock model access enabled
- AWS credentials configured (via environment variables, AWS CLI profile, or IAM instance role)

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/telecom-ai-assistant-bedrock.git
   cd telecom-ai-assistant-bedrock
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables (copy and edit):
   ```bash
   cp .env.example .env
   # Edit .env with your AWS region and preferred Bedrock model ID
   ```

4. Enable model access in [Amazon Bedrock Console](https://console.aws.amazon.com/bedrock/) for your chosen model (e.g., `us.amazon.nova-lite-v1:0` or `anthropic.claude-3-haiku-20240307-v1:0`)

5. Place the 3GPP dataset file (`3gpp_standard_telecom_dataset_updated.xlsx`) into the `data/` directory

### Run Backend

```bash
cd backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Run Frontend

```bash
export API_URL=http://127.0.0.1:8000
streamlit run frontend/streamlit_app.py
```

### Deploy to AWS (CloudFormation)

Package app and upload to S3
zip -r telecom-app.zip backend/ frontend/ data/supplemental/ requirements.txt
aws s3 cp telecom-app.zip s3://<your-bucket>/telecom-app.zip
aws s3 cp data/3gpp_standard_telecom_dataset_updated.xlsx s3://<your-bucket>/

Deploy stack (replace placeholder values with your own)
aws cloudformation deploy \
  --template-file infra/telecom-stack.yaml \
  --stack-name telecom-ai-assistant \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    S3Bucket=<your-s3-bucket> \
    VpcId=<your-vpc-id> \
    SubnetId=<your-subnet-id>

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| POST | `/chat` | Main chat endpoint (RAG + memory) |
| GET | `/severity-summary` | Incident severity counts |
| GET | `/incidents/search?q=<query>` | Search incidents by ID |
| GET | `/memory/{user_id}` | Retrieve user long-term memory |
| POST | `/memory/{session_id}/clear` | Clear session memory |

---

## Memory Model

- **Short-term memory** - Per-session conversation history stored in `data/memory/session_memory.json`. Capped to the last 16 turns. Cleared on new session.
- **Long-term memory** - Per-user persistent facts extracted heuristically (preferences, telecom domains of interest, recurring topics). Stored in `data/memory/long_term_memory.json`. Persists across sessions.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | AWS Bedrock (Amazon Nova Lite / Claude 3 Haiku) |
| Backend | Python, FastAPI, boto3 |
| Frontend | Streamlit |
| Data | 3GPP Telecom Dataset (Excel), Curated TXT knowledge |
| Retrieval | Custom weighted TF-IDF scorer with telecom domain boosting |
| Memory | JSON file-based dual-store (session + long-term) |
| Infrastructure | AWS CloudFormation, EC2, IAM, S3 |
| Dev Tooling | Cursor IDE + Agent Toolkit for AWS |

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
