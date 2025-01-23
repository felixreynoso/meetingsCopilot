# uvicorn main:app


from fastapi import FastAPI, Header, HTTPException, File, UploadFile, Form, Query
from typing import List
import logging
import os
from uuid import uuid4
import uvicorn
from dotenv import load_dotenv, find_dotenv
from IPython.display import display, Markdown
from tempfile import NamedTemporaryFile
from collections import defaultdict
# from langchain.document_loaders import CSVLoader
# from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
# from langchain.vectorstores import DocArrayInMemorySearch
# from langchain.embeddings import OpenAIEmbeddings
# from langchain.schema import Document
# from langchain_core.documents import Document
# from langchain.memory import ConversationBufferWindowMemory



from db import get_vector_store, get_document_store, get_chat_history, update_chat_history,  close_client

import bs4
from langchain import hub
from langchain_community.document_loaders import WebBaseLoader
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain.chains import create_history_aware_retriever
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.messages import HumanMessage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




# Utilities
db = get_vector_store()
chat_store = get_document_store()

retriever = db.as_retriever(
    search_type="similarity",
    search_kwargs= {"k": 2,"score_threshold":0.5},
   
)
llm = ChatOpenAI(model="gpt-3.5-turbo-0125")
prompt = hub.pull("rlm/rag-prompt")
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

contextualize_q_system_prompt = """Given a chat history and the latest user question \
which might reference context in the chat history, formulate a standalone question \
which can be understood without the chat history. Do NOT answer the question, \
just reformulate it if needed and otherwise return it as is."""
contextualize_q_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", contextualize_q_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)


qa_system_prompt = """You are an assistant for question-answering tasks. \
Use the following pieces of retrieved context to answer the question. \
If you don't know the answer, just say that you don't know. \
Use three sentences maximum and keep the answer concise.\

{context}"""
qa_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", qa_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

chat_history_dict = defaultdict(list)

# Initialize the FastAPI app
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


db = get_vector_store()

retriever = db.as_retriever(
    search_type="similarity",
    search_kwargs= {"k": 2},
)



@app.post("/extract-text")
async def extract_text_from_pdfs(
    email: str = Header(..., description="User email address"),
    files: List[UploadFile] = File(..., description="Array of PDF files"),
):
    """
    POST endpoint to extract text from an array of PDF files.
    """
    # Validate email
    if not email:
        raise HTTPException(status_code=400, detail="Email header is required")

    extracted_docs = []
    ids = []

    for file in files:
        try:
            if file.content_type != "application/pdf":
                raise HTTPException(
                    status_code=400, detail=f"{file.filename} is not a valid PDF file"
                )

            # Save the uploaded file to a temporary location
            with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                temp_file.write(file.file.read())
                temp_file_path = temp_file.name

            # Load and split PDF using PyPDFLoader
            loader = PyPDFLoader(temp_file_path)
            docs = loader.load_and_split()

            # Append metadata and collect extracted documents
            for doc in docs:
                doc.metadata["ownerId"] = email
                extracted_docs.append(doc)

            # Generate unique IDs for each document
            ids.extend([str(uuid4()) for _ in docs])

        except Exception as e:
            logger.error(f"Failed to process {file.filename}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"An error occurred while processing {file.filename}: {str(e)}",
            )
        finally:
            # Remove the temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    # Persist extracted documents to the database
    try:
        db.add_documents(extracted_docs, ids=ids)
    except Exception as e:
        logger.error(f"Failed to persist documents to the database: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Couldn't persist the documents to the database",
        )

    return {"email": email, "texts": [doc.page_content for doc in extracted_docs]}



@app.get("/prompt")
async def handle_query(
    email: str = Header(..., description="User email address"),
    query: str = Query(..., description="Query parameter to handle"),
):
    """
    GET endpoint to handle query with an email header.
    """
    # Validate email
    if not email:
        raise HTTPException(status_code=400, detail="Email header is required")


    search_filter = {"ownerId": email}
    retriever.search_kwargs["pre_filter"] = search_filter
    
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, contextualize_q_prompt
    )

    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
    rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)
    
    # chat_history = chat_history_dict[email]
    user_history = chat_store.find_one({"ownerId": email})
    
    chat_history = get_chat_history(email)

    response = rag_chain.invoke({"input": query, "chat_history": chat_history})

    # chat_history.extend([HumanMessage(content=query), response["answer"]])
    update_chat_history(email, f"HumanMessage: {query}", f"BotMessage: {response["answer"]}")

    print(chat_history, "aqui")
    return {"query": query, "owner_id": email , "result": response["answer"]}


# Start the application
if __name__ == "__main__":    
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)