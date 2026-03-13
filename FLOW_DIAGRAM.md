# Smart RAG Flow Diagram

## Simplified Workflow

```mermaid
graph LR
    A[📝 User Question] --> B[🔍 Retrieve Documents]
    B --> C[✍️ Generate Answer]
    C --> D{✅ Verify Quality}
    D -->|Good Quality| E[✓ Final Answer]
    D -->|Needs Improvement<br/>Max 3 retries| F[🔄 Refine Query]
    F --> B
    
    style A fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    style B fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    style C fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    style D fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    style E fill:#c8e6c9,stroke:#2e7d32,stroke-width:3px
    style F fill:#ffe0b2,stroke:#f57c00,stroke-width:2px
```

## How It Works

1. **User Question** - User submits a question about uploaded documents
2. **Retrieve Documents** - Vector search finds top 4 relevant document chunks
3. **Generate Answer** - LLM creates answer using only retrieved context
4. **Verify Quality** - System checks if answer is well-supported and useful
5. **Refine Query** (if needed) - Rewrites query with better keywords and retries
6. **Final Answer** - Returns validated, high-quality answer to user

## Key Features

- ✅ Grounded in document context
- ✅ Quality verification loop
- ✅ Automatic query refinement
- ✅ Maximum 3 retry attempts
- ✅ Fallback to "No answer found" if quality threshold not met
