# Documentation
# https://python.langchain.com/docs/integrations/vectorstores/mongodb_atlas/#initialization

import os
from dotenv import load_dotenv, find_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient

# Load environment variables
_ = load_dotenv(find_dotenv())  # Read local .env file

# Constants
MONGODB_ATLAS_CLUSTER_URI = os.getenv("MONGO_URI")
DB_NAME = "langchain_test_db"
COLLECTION_NAME = "langchain_test_vectorstores"
CHAT_HISTORY_COLLECTION = "chat_history"
ATLAS_VECTOR_SEARCH_INDEX_NAME = "langchain-test-index-vectorstores"

# Initialize MongoDB client
client = MongoClient(MONGODB_ATLAS_CLUSTER_URI)

# Create and export vector store
def get_vector_store():
    # Initialize collection and embeddings
    MONGODB_COLLECTION = client[DB_NAME][COLLECTION_NAME]
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", dimensions=512)

    # Initialize vector store
    vector_store = MongoDBAtlasVectorSearch(
        collection=MONGODB_COLLECTION,
        embedding=embeddings,
        index_name=ATLAS_VECTOR_SEARCH_INDEX_NAME,
        relevance_score_fn="cosine",
    )
    return vector_store


def get_document_store():
    """
    Returns a MongoDB collection as a key-value store for chat history.
    """
    document_store = client[DB_NAME][CHAT_HISTORY_COLLECTION]
    return document_store
    



def update_chat_history(email, prompt, response):
    """
    Updates the chat history for a given user. Ensures the chat history array
    does not exceed 8 items by removing the oldest items when necessary.

    Parameters:
    - email (str): The ID of the user.
    - prompt (str): The new message (prompt) to add.
    - response (str): The new response to add.
    """
    chat_store = get_document_store()
    
    # Fetch the current chat history for the user
    user_record = chat_store.find_one({"ownerId": email})

    if user_record:
        chat_history = user_record.get("chat_history", [])
        
        # Ensure the length does not exceed 8 items
        if len(chat_history) >= 8:
            chat_history = chat_history[2:]  # Remove the first two oldest items

        # Add the new prompt and response to the history
        chat_history.extend([prompt, response])
        
        # Update the database
        chat_store.update_one(
            {"ownerId": email},
            {"$set": {"chat_history": chat_history}}
        )
    else:
        # Create a new record for the user if it does not exist
        chat_store.insert_one({
            "ownerId": email,
            "chat_history": [prompt, response]
        })



def get_chat_history(email):
    """
    Retrieves the chat history for a given user. Returns an empty array if the user 
    does not exist in the database or if the chat_history for the user is empty.

    Parameters:
    - email (str): The ID of the user.

    Returns:
    - list: The chat history for the user, or an empty list if none exists.
    """
    chat_store = get_document_store()

    # Fetch the user's record from the database
    user_record = chat_store.find_one({"ownerId": email})

    if user_record and "chat_history" in user_record:
        # Return the chat history if it exists, otherwise return an empty array
        return user_record.get("chat_history", [])
    else:
        # Return an empty array if the user record doesn't exist or is missing chat_history
        return []


# Export client for proper cleanup
def close_client():
    client.close()
