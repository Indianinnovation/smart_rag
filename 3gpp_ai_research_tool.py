from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

class ResearchState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    search_results: str
    final_answer: str

search_tool = TavilySearchResults(max_results=3)

def query_analyzer(state: ResearchState):
    """Analyze and refine the user query for 3GPP AI research"""
    messages = state['messages']
    last_message = messages[-1].content
    
    refined_query = f"3GPP AI/ML specifications {last_message}"
    return {"query": refined_query}

def search_node(state: ResearchState):
    """Search for 3GPP specifications and AI research"""
    query = state['query']
    results = search_tool.invoke(query)
    
    search_summary = "\n\n".join([
        f"Source: {r['url']}\nContent: {r['content']}" 
        for r in results
    ])
    
    return {"search_results": search_summary}

def synthesize_node(state: ResearchState):
    """Synthesize findings into a comprehensive answer"""
    search_results = state.get('search_results', '')
    original_query = state['messages'][-1].content
    
    synthesis_prompt = f"""Based on the following search results about 3GPP AI research:

{search_results}

Please provide a comprehensive answer to: {original_query}

Focus on:
- Relevant 3GPP specifications (e.g., TR 38.843, TS 38.300)
- AI/ML use cases in 5G/6G
- Technical details and standards

Answer:"""
    
    response = llm.invoke([HumanMessage(content=synthesis_prompt)])
    return {"messages": [response], "final_answer": response.content}

def route_after_search(state: ResearchState) -> Literal["synthesize", END]:
    """Decide whether to synthesize or end"""
    if state.get('search_results'):
        return "synthesize"
    return END

# Build the graph
graph = StateGraph(ResearchState)
graph.add_node("analyze", query_analyzer)
graph.add_node("search", search_node)
graph.add_node("synthesize", synthesize_node)

graph.add_edge(START, "analyze")
graph.add_edge("analyze", "search")
graph.add_conditional_edges("search", route_after_search)
graph.add_edge("synthesize", END)

checkpointer = InMemorySaver()
research_agent = graph.compile(checkpointer=checkpointer)

if __name__ == "__main__":
    query = "What are the latest 3GPP standards for AI/ML in 5G networks?"
    
    result = research_agent.invoke(
        {'messages': [HumanMessage(content=query)]},
        config={'configurable': {'thread_id': 'research-1'}}
    )
    
    print("\n=== 3GPP AI Research Results ===\n")
    print(result['final_answer'])
