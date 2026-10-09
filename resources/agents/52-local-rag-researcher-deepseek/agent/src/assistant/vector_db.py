import os
from langchain_community.document_loaders import DirectoryLoader
from langchain_experimental.text_splitter import SemanticChunker 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

VECTOR_DB_PATH = "database"
 
def get_or_create_vector_db():
    """Get or create the vector DB."""
    embeddings = HuggingFaceEmbeddings()

    if os.path.exists(VECTOR_DB_PATH) and os.listdir(VECTOR_DB_PATH):
        # Use the existing vector store
        vectorstore = Chroma(persist_directory=VECTOR_DB_PATH, embedding_function=embeddings)
    else:
        # Load documents and create a new vector store
        loader = DirectoryLoader("./files")
        docs = loader.load()

        # Process the new documents
        semantic_text_splitter = SemanticChunker(embeddings)
        documents = semantic_text_splitter.split_documents(docs)

        # Split resulting documents into smaller chunks SemanticChunker
        # doesn't have a max chunk size parameter, so we use 
        # RecursiveCharacterTextSplitter to avoid having large chunks
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=400)
        split_documents = text_splitter.split_documents(documents)
        vectorstore = Chroma.from_documents(split_documents, embeddings, persist_directory=VECTOR_DB_PATH)

    return vectorstore

def add_documents(documents):
    """
    Add new documents to the existing vector store.

    Args:
        documents: List of documents to add to the vector store
    """
    embeddings = HuggingFaceEmbeddings()
    
    # Process the new documents
    semantic_text_splitter = SemanticChunker(embeddings)
    documents = semantic_text_splitter.split_documents(documents)

    # Split resulting documents into smaller chunks SemanticChunker
    # doesn't have a max chunk size parameter, so we use 
    # RecursiveCharacterTextSplitter to avoid having large chunks
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=400)
    split_documents = text_splitter.split_documents(documents)

    if os.path.exists(VECTOR_DB_PATH) and os.listdir(VECTOR_DB_PATH):
        # Add to existing vector store
        vectorstore = Chroma(persist_directory=VECTOR_DB_PATH, embedding_function=embeddings)
        vectorstore.add_documents(split_documents)
    else:
        # Create new vector store if it doesn't exist
        vectorstore = Chroma.from_documents(
            split_documents,
            embeddings,
            persist_directory=VECTOR_DB_PATH
        )

    return vectorstore