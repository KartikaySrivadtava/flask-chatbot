import os
import time
import re
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import AzureOpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from docx2pdf import convert  

# -------------------- ENV --------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")

FILES_FOLDER = "./pdfs"
BASE_PERSIST_DIR = "./chroma_dbs"

# -------------------- EMBEDDINGS --------------------
embeddings = AzureOpenAIEmbeddings(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_deployment=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    openai_api_key=OPENAI_API_KEY,
    chunk_size=8,  # ✅ helps avoid Azure overload
)

# -------------------- CHUNKING --------------------
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=100,
)

# -------------------- HELPERS --------------------
def sanitize_name(name: str) -> str:
    name = Path(name).stem
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)

def convert_docx_to_pdf(docx_path: str) -> str:
    """
    Converts DOCX to PDF using MS Word (docx2pdf).
    Returns generated pdf path.
    """
    docx_path = Path(docx_path)
    pdf_path = docx_path.with_suffix(".pdf")

    # If already exists, reuse
    if pdf_path.exists():
        return str(pdf_path)

    print(f"📝 Converting DOCX -> PDF: {docx_path.name}")
    convert(str(docx_path), str(pdf_path))
    return str(pdf_path)

def load_file_with_real_pages(file_path: str):
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        docs = PyPDFLoader(file_path).load()
        return docs, "pdf"

    if ext == ".docx":
        pdf_path = convert_docx_to_pdf(file_path)
        docs = PyPDFLoader(pdf_path).load()   # ✅ real pages now
        return docs, "docx"

    return [], None

def create_chroma_with_retry(chunks, persist_dir, max_retries=8):
    attempt = 0
    while True:
        try:
            return Chroma.from_documents(
                documents=chunks,
                embedding=embeddings,
                persist_directory=persist_dir,
            )

        except Exception as e:
            msg = str(e).lower()
            if ("429" in msg) or ("nocapacity" in msg) or ("rate limit" in msg):
                attempt += 1
                if attempt > max_retries:
                    raise

                wait_time = 10 * attempt
                print(f"⚠️ Azure overloaded (429). Retrying in {wait_time}s... [{attempt}/{max_retries}]")
                time.sleep(wait_time)
                continue

            raise

# -------------------- PROCESS FILES --------------------
os.makedirs(BASE_PERSIST_DIR, exist_ok=True)

for filename in os.listdir(FILES_FOLDER):
    if not filename.lower().endswith((".pdf", ".docx")):
        continue

    file_path = os.path.join(FILES_FOLDER, filename)
    safe_name = sanitize_name(filename)
    db_name = f"chroma_{safe_name}"
    persist_dir = os.path.join(BASE_PERSIST_DIR, db_name)

    print(f"\n📌 Processing: {filename}")
    print(f"📂 DB Folder: {persist_dir}")

    documents, doc_type = load_file_with_real_pages(file_path)
    if not documents:
        print("⚠️ Skipped: unsupported file")
        continue

    print(f"Loaded {len(documents)} pages")

    # ✅ chunk
    chunks = text_splitter.split_documents(documents)

    # ✅ attach metadata at chunk level
    for i, c in enumerate(chunks):
        c.metadata = c.metadata or {}
        c.metadata.update({
            "source": filename,
            "doc_type": doc_type,
            "db_name": db_name,
            "chunk_id": i,
        })

        # ✅ PyPDFLoader returns page=0,1,2...
        # We'll keep it. In citations you can show page+1 if needed.
        if "page" not in c.metadata:
            c.metadata["page"] = "N/A"

    print(f"Created {len(chunks)} chunks")

    # ✅ create db
    create_chroma_with_retry(chunks, persist_dir)
    print(f"✅ DB created: {db_name}")

print("\n🎉 Done")
