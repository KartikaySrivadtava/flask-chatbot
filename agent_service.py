# agent_service.py
import os
import re
from dotenv import load_dotenv
from collections import OrderedDict
from pathlib import Path

from langchain_chroma import Chroma
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_core.tools import Tool

from langchain_classic.memory import ConversationBufferMemory
from langchain_classic.agents import AgentExecutor, ZeroShotAgent
from langchain_classic.chains import LLMChain


# -------------------- ENV --------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")

CHROMA_BASE_DIR = "./chroma_dbs"   # ✅ all per-file DBs here


# -------------------- EMBEDDINGS --------------------
embeddings = AzureOpenAIEmbeddings(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    openai_api_key=OPENAI_API_KEY,
)


# -------------------- STYLE VECTORSTORE --------------------
style_vectorstore = Chroma(
    persist_directory="./chroma_style_db",
    embedding_function=embeddings
)


# -------------------- LOAD ALL CHROMA DBs DYNAMICALLY --------------------
def load_all_chroma_dbs(base_dir: str):
    base = Path(base_dir)
    if not base.exists():
        print(f"⚠️ Chroma base directory not found: {base_dir}")
        return {}

    dbs = {}
    for folder in base.iterdir():
        if folder.is_dir() and folder.name.startswith("chroma_"):
            db_name = folder.name
            dbs[db_name] = Chroma(
                persist_directory=str(folder),
                embedding_function=embeddings
            )
    return dbs


vectorstores = load_all_chroma_dbs(CHROMA_BASE_DIR)

print("\n✅ Loaded Chroma DBs:")
for k in vectorstores.keys():
    print(" -", k)

if not vectorstores:
    print("⚠️ No vectorstores found in chroma_dbs folder.")


# -------------------- CONVERSATIONAL MEMORY --------------------
memory = ConversationBufferMemory(
    memory_key="chat_history",
    input_key="input",
    output_key="output",
    return_messages=False
)


# -------------------- GENERIC SEARCH --------------------
def search_pdf_from_db(vectorstore: Chroma, query: str, k: int = 8) -> dict:
    docs_with_scores = vectorstore.similarity_search_with_score(query, k=12)

    # ✅ distance threshold
    docs = [doc for doc, score in docs_with_scores if score < 0.38][:k]

    if not docs:
        return {"context": "", "citations": []}

    citations = OrderedDict()
    context_blocks = []

    for doc in docs:
        meta = doc.metadata or {}
        source = meta.get("source", "Unknown")
        page = meta.get("page", None)
        db_name = meta.get("db_name", "UnknownDB")

        # ✅ only cite if page is numeric
        if isinstance(page, int):
            page = page + 1  # convert to 1-based
            citations[f"{source}, Page {page}"] = None

        context_blocks.append(
            f"DB: {db_name}\nSource: {source}, Page: {page if isinstance(page, int) else 'N/A'}\n{doc.page_content}"
        )

    return {
        "context": "\n\n---\n\n".join(context_blocks),
        "citations": list(citations.keys())
    }


# -------------------- STYLE RETRIEVAL --------------------
def retrieve_style_examples(query: str, k: int = 5) -> str:
    results = style_vectorstore.similarity_search(query, k=k)
    return "\n\n".join(
        [f"Example {i+1}:\n{doc.page_content}" for i, doc in enumerate(results)]
    )


# -------------------- TOOL OUTPUT FORMATTING --------------------
def format_context_with_citations(res: dict) -> str:
    context = res.get("context", "").strip()
    citations = res.get("citations", [])

    if not context:
        return ""

    citation_block = ""
    if citations:
        citation_block = "\n\nCitations:\n" + "\n".join(f"- {c}" for c in citations)

    return context + citation_block


# -------------------- TOOL FACTORY --------------------
def make_db_tool(db_name: str, vectorstore: Chroma) -> Tool:
    def _tool(query: str) -> str:
        res = search_pdf_from_db(vectorstore, query)
        return format_context_with_citations(res)

    return Tool(
        name=f"PDFRetriever_{db_name}",
        func=_tool,
        description=f"Use this tool to search in {db_name}."
    )


# -------------------- BUILD TOOLS --------------------
tools = []

# ✅ One tool per DB
for db_name, vs in vectorstores.items():
    tools.append(make_db_tool(db_name, vs))


# ✅ Fallback tool: search all DBs
def pdf_retriever_all(query: str) -> str:
    results = []
    for db_name, vs in vectorstores.items():
        results.append((db_name, search_pdf_from_db(vs, query, k=5)))

    blocks = []
    citations = OrderedDict()

    for db_name, res in results:
        if not res["context"]:
            continue
        blocks.append(f"=== {db_name} ===\n{res['context']}")
        for c in res["citations"]:
            citations[c] = None

    if not blocks:
        return ""

    final_context = "\n\n---\n\n".join(blocks)

    citation_block = ""
    if citations:
        citation_block = "\n\nCitations:\n" + "\n".join(f"- {c}" for c in citations.keys())

    return final_context + citation_block


tools.append(
    Tool(
        name="PDFRetriever_ALL",
        func=pdf_retriever_all,
        description="Use ONLY if question is broad or you are unsure which DB to use; searches all DBs."
    )
)


# -------------------- LLM --------------------
llm = AzureChatOpenAI(
    azure_deployment=AZURE_OPENAI_DEPLOYMENT,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=OPENAI_API_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    temperature=0.2,
    max_tokens=9000,
)


# -------------------- PROMPT --------------------
prefix = """You are a helpful and professional finance assistant.

Conversation so far:
{chat_history}

You have access to multiple PDF retriever tools (one per DB).

RULES:
1) Always choose the most relevant retriever tool based on the question.
2) Use retrieved context to answer.
3) If context is empty or answer is not supported by context, provide your best answer from the context only along with references.
4) Follow the same style, tone and format as provided Style Examples.
5) Answer the question in the same language in which the user has asked the question.
"""

suffix = """Begin!

Question: {input}
Style Examples: {style_examples}

You may use the retriever tools.
After reasoning, always finish with your response in this exact format:

Final Answer:
<your completed, human-readable answer here>

{agent_scratchpad}
"""

custom_prompt = ZeroShotAgent.create_prompt(
    tools=tools,
    prefix=prefix,
    suffix=suffix,
    input_variables=["input", "style_examples", "chat_history", "agent_scratchpad"],
)


# -------------------- AGENT --------------------
llm_chain = LLMChain(llm=llm, prompt=custom_prompt)
agent = ZeroShotAgent(llm_chain=llm_chain, tools=tools)

agent_executor = AgentExecutor.from_agent_and_tools(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True,
    handle_parsing_errors=True,
    early_stopping_method="generate",
    return_intermediate_steps=True,
)


# -------------------- CITATION EXTRACTION --------------------
def extract_citations(text: str) -> list:
    citations = []
    if not text or "Citations:" not in text:
        return citations

    part = text.split("Citations:", 1)[1]
    for line in part.splitlines():
        line = line.strip()
        if line.startswith("-"):
            c = line[1:].strip()
            # ✅ do not include N/A citations
            if "Page N/A" in c:
                continue
            citations.append(c)
    return citations


def remove_existing_citations(answer: str) -> str:
    """
    If LLM already printed citations, remove them.
    We'll append our own citations only once.
    """
    return re.split(r"\n\s*Citations\s*:\s*\n", answer, maxsplit=1)[0].strip()


# -------------------- PUBLIC API FUNCTION --------------------
def ask_agent(question: str) -> str:
    if not vectorstores:
        return "Knowledge base is empty (no Chroma DBs found)."

    style_examples = retrieve_style_examples(question)

    result = agent_executor.invoke({
        "input": question,
        "style_examples": style_examples
    })

    # ✅ remove citations if LLM prints them
    answer = remove_existing_citations(result["output"])

    # ✅ Collect citations from tool observations
    citations = OrderedDict()
    for action, observation in result.get("intermediate_steps", []):
        for c in extract_citations(observation):
            citations[c] = None

    # ✅ Append citations ONCE
    if citations:
        answer += "\n\nCitations:\n" + "\n".join([f"- {c}" for c in citations.keys()])

    return answer
