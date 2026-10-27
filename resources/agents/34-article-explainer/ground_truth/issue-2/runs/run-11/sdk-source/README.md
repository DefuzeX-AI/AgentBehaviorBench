# Article Explainer

An intelligent document analysis tool that helps you understand complex technical articles through AI-powered
explanations, analogies, and summaries. A good introduction to the Swarm Architecture from LangChain.

Article I wrote about Swarm at: https://medium.com/@caldasdcardoso/swarm-architecture-agents-in-langgraph-b8b1b53c61b3

LangChain documentation at: https://langchain-ai.github.io/langgraph/agents/multi-agent/#swarm

## Features

- **PDF Upload & Processing**: Upload technical documents and get instant access for asking questions
- **Multi-Expert System**: Specialized agents work together to provide comprehensive explanations
- **PDF Viewer**: See your PDF within the main page for added context
- **Interactive Chat Interface**: Ask questions and get tailored responses
- **Smart Collaboration**: Agents automatically work together for complex queries
- **Document Analysis Tools**: Extract key terms, analyze structure, and assess complexity

## Application

### Usage explanation and interface
![img.png](misc/img.png)

### Interactive chat with the agentic team
![img_1.png](misc/img_1.png)


## Quick Start

### Installation

(If you have not set up uv yet, visit: https://docs.astral.sh/uv/getting-started/installation/)

1. Install dependencies:

```bash
uv sync
```

2. Set up environment variables:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

### Usage

#### Docker 

1. Build and run with Docker Compose:

```bash
docker build -t article_explainer .
docker compose up -d
```

2. Open your browser at `http://localhost:8501`

#### Web Interface (Local development)

Launch the Streamlit web interface:

```bash
uv run streamlit run article_explainer_page.py
```

1. Open your browser at `http://localhost:8501`

## Example Queries

- "Summarize this document"
- "Explain the most complex concepts with analogies"
- "Provide code samples for the most interesting topics"
- "Give me a TL;DR with the key technical details"
- "Are there security vulnerabilities associated with the content?"
