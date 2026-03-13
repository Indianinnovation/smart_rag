# Smart RAG (Self-RAG Step 7) – Streamlit Portal

Professional Smart RAG application built with:

- LangGraph workflow orchestration
- LangChain retrieval and chunking
- FAISS vector store
- OpenAI embeddings and chat model
- Streamlit frontend with streaming answer output

## Features

- Upload one or more PDF files
- Build retrieval index from uploaded files
- Self-RAG flow:
  - retrieval decision
  - retrieval + relevance filtering
  - grounded generation
  - support verification (`IsSUP`)
  - usefulness verification (`IsUSE`)
  - query rewrite retry loop
- Professional UI and diagnostics panel
- Graceful fallback parser handling for difficult PDFs

## Main App

- Streamlit app: [streamlit_smart_rag.py](streamlit_smart_rag.py)

## Setup

1. Create and activate your Python environment.
2. Install dependencies:

```bash
pip install -U streamlit langchain langgraph langchain-community langchain-openai faiss-cpu pypdf python-dotenv
```

3. Create your environment file:

```bash
cp .env.example .env
```

4. Fill keys in `.env`:

- `OPENAI_API_KEY`
- `TAVILY_API_KEY` (only if used in your flows)

## Run

```bash
streamlit run streamlit_smart_rag.py
```

## Security Notes

- Do **not** commit `.env`.
- Rotate any keys that were ever exposed in plaintext.
- Use `.env.example` for sharing required variables safely.

## Suggested GitHub Publish Steps

```bash
git init
git add .
git commit -m "Initial Smart RAG Streamlit app"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

