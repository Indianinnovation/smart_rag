from __future__ import annotations

import tempfile
import time
from typing import List, Literal, TypedDict

import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from langgraph.graph import END, START, StateGraph

load_dotenv()


# -----------------------------
# Graph state
# -----------------------------
class State(TypedDict):
	question: str
	retrieval_query: str
	rewrite_tries: int

	need_retrieval: bool
	docs: List[Document]
	relevant_docs: List[Document]
	context: str
	answer: str

	issup: Literal["fully_supported", "partially_supported", "no_support"]
	evidence: List[str]
	retries: int

	isuse: Literal["useful", "not_useful"]
	use_reason: str


# -----------------------------
# Structured outputs
# -----------------------------
class RetrieveDecision(BaseModel):
	should_retrieve: bool = Field(
		...,
		description="True if document retrieval is needed to answer reliably.",
	)


class RelevanceDecision(BaseModel):
	is_relevant: bool = Field(
		...,
		description="True when the chunk is topically relevant to the question.",
	)


class IsSUPDecision(BaseModel):
	issup: Literal["fully_supported", "partially_supported", "no_support"]
	evidence: List[str] = Field(default_factory=list)


class IsUSEDecision(BaseModel):
	isuse: Literal["useful", "not_useful"]
	reason: str = Field(..., description="Short one-line reason.")


class RewriteDecision(BaseModel):
	retrieval_query: str


# -----------------------------
# Prompts
# -----------------------------
decide_retrieval_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"You decide whether retrieval is needed.\n"
			"Return JSON with key: should_retrieve (boolean).\n\n"
			"Guidelines:\n"
			"- should_retrieve=True if answering requires specific facts from uploaded documents.\n"
			"- should_retrieve=False for general explanations/definitions.\n"
			"- If unsure, choose True.",
		),
		("human", "Question: {question}"),
	]
)


direct_generation_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"Answer using only your general knowledge.\n"
			"If the question requires specific document details, say:\n"
			"'I don't know based on my general knowledge.'",
		),
		("human", "{question}"),
	]
)


is_relevant_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"You are judging chunk relevance at a TOPIC level.\n"
			"Return JSON matching the schema.\n\n"
			"A chunk is relevant if it discusses the same entity/topic area as the question.\n"
			"It does not need to fully answer the question.\n"
			"Do not evaluate factual support here.\n"
			"When unsure, return is_relevant=true.",
		),
		("human", "Question:\n{question}\n\nChunk:\n{document}"),
	]
)


rag_generation_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"You are a professional business assistant.\n"
			"Answer the user question strictly using the provided context.\n"
			"Do not mention that context was provided.",
		),
		("human", "Question:\n{question}\n\nContext:\n{context}"),
	]
)


issup_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"You verify whether the ANSWER is supported by CONTEXT.\n"
			"Return JSON with keys: issup, evidence.\n"
			"issup must be one of: fully_supported, partially_supported, no_support.\n"
			"Be strict and do not use outside knowledge.",
		),
		(
			"human",
			"Question:\n{question}\n\nAnswer:\n{answer}\n\nContext:\n{context}",
		),
	]
)


revise_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"You are a strict reviser.\n"
			"Revise the answer to be fully grounded in context and concise.",
		),
		(
			"human",
			"Question:\n{question}\n\nCurrent Answer:\n{answer}\n\nContext:\n{context}",
		),
	]
)


isuse_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"You judge usefulness of ANSWER for QUESTION.\n"
			"Return JSON with keys: isuse, reason.\n"
			"- useful: directly answers the question.\n"
			"- not_useful: generic, off-topic, or incomplete.",
		),
		("human", "Question:\n{question}\n\nAnswer:\n{answer}"),
	]
)


rewrite_prompt = ChatPromptTemplate.from_messages(
	[
		(
			"system",
			"Rewrite QUESTION into a short retrieval query for vector search over uploaded PDFs.\n"
			"Rules:\n"
			"- Keep 6-16 words\n"
			"- Preserve key entities\n"
			"- Add high-signal keywords\n"
			"- Do not answer the question\n"
			"Return JSON key: retrieval_query",
		),
		(
			"human",
			"Question:\n{question}\n\nPrevious retrieval query:\n{retrieval_query}\n\nCurrent answer:\n{answer}",
		),
	]
)


MAX_RETRIES = 5
MAX_REWRITE_TRIES = 3


def build_graph(retriever):
	llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
	should_retrieve_llm = llm.with_structured_output(RetrieveDecision)
	relevance_llm = llm.with_structured_output(RelevanceDecision)
	issup_llm = llm.with_structured_output(IsSUPDecision)
	isuse_llm = llm.with_structured_output(IsUSEDecision)
	rewrite_llm = llm.with_structured_output(RewriteDecision)

	def decide_retrieval(state: State):
		decision: RetrieveDecision = should_retrieve_llm.invoke(
			decide_retrieval_prompt.format_messages(question=state["question"])
		)
		return {"need_retrieval": decision.should_retrieve}

	def route_after_decide(state: State):
		return "retrieve" if state["need_retrieval"] else "generate_direct"

	def generate_direct(state: State):
		out = llm.invoke(
			direct_generation_prompt.format_messages(question=state["question"])
		)
		return {"answer": out.content}

	def retrieve(state: State):
		query = state.get("retrieval_query") or state["question"]
		return {"docs": retriever.invoke(query)}

	def is_relevant(state: State):
		relevant_docs: List[Document] = []
		for doc in state.get("docs", []):
			decision: RelevanceDecision = relevance_llm.invoke(
				is_relevant_prompt.format_messages(
					question=state["question"], document=doc.page_content
				)
			)
			if decision.is_relevant:
				relevant_docs.append(doc)
		return {"relevant_docs": relevant_docs}

	def route_after_relevance(state: State):
		if state.get("relevant_docs"):
			return "generate_from_context"
		return "no_answer_found"

	def generate_from_context(state: State):
		context = "\n\n---\n\n".join(
			d.page_content for d in state.get("relevant_docs", [])
		).strip()
		if not context:
			return {"answer": "No answer found.", "context": ""}
		out = llm.invoke(
			rag_generation_prompt.format_messages(
				question=state["question"],
				context=context,
			)
		)
		return {"answer": out.content, "context": context}

	def no_answer_found(_: State):
		return {"answer": "No answer found.", "context": ""}

	def is_sup(state: State):
		decision: IsSUPDecision = issup_llm.invoke(
			issup_prompt.format_messages(
				question=state["question"],
				answer=state.get("answer", ""),
				context=state.get("context", ""),
			)
		)
		return {"issup": decision.issup, "evidence": decision.evidence}

	def route_after_issup(state: State):
		if state.get("issup") == "fully_supported":
			return "accept_answer"
		if state.get("retries", 0) >= MAX_RETRIES:
			return "accept_answer"
		return "revise_answer"

	def revise_answer(state: State):
		out = llm.invoke(
			revise_prompt.format_messages(
				question=state["question"],
				answer=state.get("answer", ""),
				context=state.get("context", ""),
			)
		)
		return {"answer": out.content, "retries": state.get("retries", 0) + 1}

	def accept_answer(_: State):
		return {}

	def is_use(state: State):
		decision: IsUSEDecision = isuse_llm.invoke(
			isuse_prompt.format_messages(
				question=state["question"], answer=state.get("answer", "")
			)
		)
		return {"isuse": decision.isuse, "use_reason": decision.reason}

	def route_after_isuse(state: State):
		if state.get("isuse") == "useful":
			return "END"
		if state.get("rewrite_tries", 0) >= MAX_REWRITE_TRIES:
			return "no_answer_found"
		return "rewrite_question"

	def rewrite_question(state: State):
		decision: RewriteDecision = rewrite_llm.invoke(
			rewrite_prompt.format_messages(
				question=state["question"],
				retrieval_query=state.get("retrieval_query", ""),
				answer=state.get("answer", ""),
			)
		)
		return {
			"retrieval_query": decision.retrieval_query,
			"rewrite_tries": state.get("rewrite_tries", 0) + 1,
			"docs": [],
			"relevant_docs": [],
			"context": "",
		}

	g = StateGraph(State)
	g.add_node("decide_retrieval", decide_retrieval)
	g.add_node("generate_direct", generate_direct)
	g.add_node("retrieve", retrieve)
	g.add_node("is_relevant", is_relevant)
	g.add_node("generate_from_context", generate_from_context)
	g.add_node("no_answer_found", no_answer_found)
	g.add_node("is_sup", is_sup)
	g.add_node("revise_answer", revise_answer)
	g.add_node("accept_answer", accept_answer)
	g.add_node("is_use", is_use)
	g.add_node("rewrite_question", rewrite_question)

	g.add_edge(START, "decide_retrieval")
	g.add_conditional_edges(
		"decide_retrieval",
		route_after_decide,
		{"generate_direct": "generate_direct", "retrieve": "retrieve"},
	)
	g.add_edge("generate_direct", END)

	g.add_edge("retrieve", "is_relevant")
	g.add_conditional_edges(
		"is_relevant",
		route_after_relevance,
		{
			"generate_from_context": "generate_from_context",
			"no_answer_found": "no_answer_found",
		},
	)

	g.add_edge("generate_from_context", "is_sup")
	g.add_conditional_edges(
		"is_sup",
		route_after_issup,
		{"accept_answer": "accept_answer", "revise_answer": "revise_answer"},
	)
	g.add_edge("revise_answer", "is_sup")

	g.add_edge("accept_answer", "is_use")
	g.add_conditional_edges(
		"is_use",
		route_after_isuse,
		{
			"END": END,
			"rewrite_question": "rewrite_question",
			"no_answer_found": "no_answer_found",
		},
	)
	g.add_edge("rewrite_question", "retrieve")

	g.add_edge("no_answer_found", END)
	return g.compile()


def load_documents_from_uploads(uploaded_files) -> List[Document]:
	docs: List[Document] = []
	failed_files: List[str] = []
	fallback_used: List[str] = []

	def _fallback_extract_with_pypdf(tmp_path: str, original_name: str) -> List[Document]:
		"""Fallback text extraction that skips broken pages instead of failing whole file."""
		try:
			reader = PdfReader(tmp_path, strict=False)
		except Exception:
			return []

		out_docs: List[Document] = []
		for page_idx, page in enumerate(reader.pages, start=1):
			text = ""

			# Try default extraction first
			try:
				text = page.extract_text() or ""
			except Exception:
				text = ""

			# Try layout extraction as backup (supported in newer pypdf)
			if not text.strip():
				try:
					text = page.extract_text(extraction_mode="layout") or ""
				except Exception:
					text = ""

			if text.strip():
				out_docs.append(
					Document(
						page_content=text,
						metadata={"source": original_name, "page": page_idx},
					)
				)

		return out_docs

	for uploaded in uploaded_files:
		try:
			with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
				tmp.write(uploaded.getvalue())
				tmp_path = tmp.name

			loaded = []
			try:
				loaded = PyPDFLoader(tmp_path).load()
			except Exception:
				loaded = []

			# If primary loader fails or returns empty text, use fallback parser.
			has_text = any((d.page_content or "").strip() for d in loaded)
			if has_text:
				docs.extend(loaded)
				continue

			fallback_docs = _fallback_extract_with_pypdf(tmp_path, uploaded.name)
			if fallback_docs:
				docs.extend(fallback_docs)
				fallback_used.append(uploaded.name)
			else:
				failed_files.append(uploaded.name)
		except Exception:
			failed_files.append(uploaded.name)

	if fallback_used:
		st.info(
			"Fallback parser used for: " + ", ".join(fallback_used)
		)

	if failed_files:
		st.warning(
			"Some files could not be parsed and were skipped: "
			+ ", ".join(failed_files)
		)

	return docs


def build_retriever_from_docs(docs: List[Document]):
	chunks = RecursiveCharacterTextSplitter(
		chunk_size=700,
		chunk_overlap=150,
	).split_documents(docs)

	if not chunks:
		raise ValueError("No text chunks created from uploaded documents.")

	embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
	vector_store = FAISS.from_documents(chunks, embeddings)
	return vector_store.as_retriever(search_kwargs={"k": 4})


def render_professional_header():
	st.set_page_config(page_title="Smart RAG Portal", page_icon="📘", layout="wide")
	st.markdown(
		"""
		<style>
			.title {font-size: 2rem; font-weight: 700; margin-bottom: 0.2rem;}
			.subtitle {color: #6b7280; margin-bottom: 1.2rem;}
			.answer-box {
				border: 1px solid #e5e7eb;
				border-radius: 12px;
				padding: 1rem;
				background: #ffffff;
			}
		</style>
		""",
		unsafe_allow_html=True,
	)
	st.markdown('<div class="title">Smart RAG Document Q&A Portal</div>', unsafe_allow_html=True)
	st.markdown(
		'<div class="subtitle">Upload PDF files and get grounded answers with support and usefulness checks.</div>',
		unsafe_allow_html=True,
	)


def stream_answer_text(text: str, delay: float = 0.012):
	"""Stream answer text word-by-word for a live response effect."""
	if not text:
		yield "No answer found."
		return

	for word in text.split(" "):
		yield word + " "
		time.sleep(delay)


def main():
	render_professional_header()

	left, right = st.columns([1, 2], gap="large")

	with left:
		st.subheader("Upload & Settings")
		uploaded_files = st.file_uploader(
			"Upload PDF documents",
			type=["pdf"],
			accept_multiple_files=True,
			help="You can upload multiple PDFs in one run.",
		)
		question = st.text_area(
			"Question",
			placeholder="Ask a specific question about your uploaded documents...",
			height=120,
		)
		run_btn = st.button("Generate Answer", type="primary", use_container_width=True)

	with right:
		st.subheader("Answer")
		answer_placeholder = st.empty()
		diag_placeholder = st.empty()

	if not run_btn:
		return

	if not uploaded_files:
		st.error("Please upload at least one PDF.")
		return

	if not question.strip():
		st.error("Please enter a question.")
		return

	with st.spinner("Processing documents and generating grounded answer..."):
		docs = load_documents_from_uploads(uploaded_files)
		if not docs:
			st.error("No readable text found in uploaded files.")
			return

		try:
			retriever = build_retriever_from_docs(docs)
		except Exception as e:
			st.error(f"Could not build retriever: {str(e)}")
			return

		app = build_graph(retriever)

		initial_state: State = {
			"question": question.strip(),
			"retrieval_query": question.strip(),
			"rewrite_tries": 0,
			"need_retrieval": True,
			"docs": [],
			"relevant_docs": [],
			"context": "",
			"answer": "",
			"issup": "no_support",
			"evidence": [],
			"retries": 0,
			"isuse": "not_useful",
			"use_reason": "",
		}

		result = app.invoke(initial_state, config={"recursion_limit": 80})

	with answer_placeholder.container():
		st.markdown('<div class="answer-box">', unsafe_allow_html=True)
		st.write_stream(stream_answer_text(result.get("answer", "No answer found.")))
		st.markdown("</div>", unsafe_allow_html=True)

	with diag_placeholder.expander("Execution Details", expanded=False):
		c1, c2, c3 = st.columns(3)
		c1.metric("Retrieved Docs", len(result.get("docs", []) or []))
		c2.metric("Relevant Docs", len(result.get("relevant_docs", []) or []))
		c3.metric("Rewrite Tries", result.get("rewrite_tries", 0))

		st.write(
			{
				"need_retrieval": result.get("need_retrieval"),
				"issup": result.get("issup"),
				"isuse": result.get("isuse"),
				"use_reason": result.get("use_reason"),
				"evidence": result.get("evidence", []),
				"support_retries": result.get("retries", 0),
			}
		)


if __name__ == "__main__":
	main()
