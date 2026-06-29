from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from connectors.gdrive import get_files_to_sync, download_items, SCOPES, TOKEN_FILE
from google_auth_oauthlib.flow import Flow
from processing.parser import process_single_file
from embedding.embedder import embed_chunks
from search.vector_store import add_to_faiss, search_faiss, get_document_metadata, load_faiss_index, save_faiss_index, add_chunks_to_index, load_chunks
from groq import Groq
import os
import hashlib

router = APIRouter()

# Simple in-memory cache for LLM responses
llm_cache = {}
oauth_states = {}

@router.get("/documents")
def list_documents():
    try:
        from connectors.gdrive import get_drive_service
        try:
            service = get_drive_service()
            about = service.about().get(fields="user").execute()
            user_email = about['user']['emailAddress']
        except Exception:
            user_email = "default_user"

        docs = list(files_collection.find({"user_email": user_email}))
        doc_ids = set()
        for d in docs:
            fid = d.get("file_id") or d.get("id")
            if fid:
                doc_ids.add(fid)

        chunks = load_chunks()
        indexed_doc_ids = set()
        for c in chunks:
            doc_id = c.get("doc_id")
            if doc_id:
                base_doc_id = doc_id.split('_chunk_')[0] if '_chunk_' in doc_id else doc_id
                if not doc_ids or base_doc_id in doc_ids:
                    indexed_doc_ids.add(base_doc_id)

        result = []
        for d in docs:
            fid = d.get("file_id") or d.get("id")
            name = d.get("name")
            if not fid or not name:
                continue
            result.append({
                "id": fid,
                "name": name,
                "status": "Indexed" if fid in indexed_doc_ids else ("Indexing" if user_email in active_syncs else "Not Indexed")
            })

        return {"documents": result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"documents": []}

@router.get("/auth/status")
def auth_status():
    try:
        is_authenticated = os.path.exists(TOKEN_FILE)
        return {"authenticated": is_authenticated}
    except Exception as e:
        return {"authenticated": False, "error": str(e)}

@router.get("/auth/login")
def auth_login():
    try:
        FRONTEND_URL = os.getenv("FRONTEND_URL", "https://hiighwatch-rag.vercel.app")
        API_URL = os.getenv("API_URL", "https://hiighwatch-rag-3cdc.onrender.com")
        
        # We store the oauth state in a JSON file to survive FastAPI hot reloads
        # IMPORTANT: explicitly request access_type='offline' AND prompt='consent'
        # so Google ALWAYS returns a refresh_token, even if the user has authorized before.
        
        credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        if not os.path.exists(credentials_path):
            raise Exception(f"OAuth credentials file not found at {credentials_path}. Please download it from Google Cloud Console.")
            
        flow = Flow.from_client_secrets_file(
            credentials_path,
            scopes=SCOPES,
            redirect_uri=f"{API_URL}/auth/callback"
        )
        auth_url, state = flow.authorization_url(
            prompt='consent', 
            access_type='offline',
            include_granted_scopes='true'
        )
        
        import json
        states_file = "oauth_states.json"
        
        # Load existing states
        states = {}
        if os.path.exists(states_file):
            with open(states_file, "r") as f:
                try:
                    content = f.read().strip()
                    if content:
                        states = json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse oauth_states.json: {e}. Starting fresh.")
                    states = {}
                except Exception as e:
                    print(f"Warning: Error reading oauth_states.json: {e}")
                    pass
                    
        # Save new state
        states[state] = flow.code_verifier
        with open(states_file, "w") as f:
            json.dump(states, f)
        
        return RedirectResponse(url=auth_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/storage/stats")
def get_storage_stats():
    try:
        from search.vector_store import load_faiss_index, load_chunks
        from db import files_collection
        import os
        from connectors.gdrive import get_drive_service
        import time
        
        user_email = None
        try:
            service = get_drive_service()
            about = service.about().get(fields="user").execute()
            user_email = about['user']['emailAddress']
        except Exception:
            pass
        
        index = load_faiss_index()
        vector_count = index.ntotal if index else 0

        chunks = load_chunks()
        progress = sync_progress.get(user_email) if user_email else None
        stage = progress.get("stage") if progress else None
        is_processing = bool(user_email and ((user_email in active_syncs) or (stage and stage not in ("done", "error"))))
        is_error = bool(stage == "error")

        if is_error:
            processing_status = "Error"
        else:
            processing_status = "Processing in background..." if is_processing else "Ready"
        
        # Estimate FAISS file size
        faiss_size_bytes = 0
        if os.path.exists("synced_docs/faiss.index"):
            faiss_size_bytes = os.path.getsize("synced_docs/faiss.index")
            
        # Get total size of synced files directory
        docs_size_bytes = 0
        docs_count = 0
        if os.path.exists("synced_docs"):
            for f in os.listdir("synced_docs"):
                fp = os.path.join("synced_docs", f)
                if os.path.isfile(fp):
                    docs_size_bytes += os.path.getsize(fp)
                    docs_count += 1

        docs_synced = 0
        if user_email:
            try:
                docs_synced = files_collection.count_documents({"user_email": user_email})
            except Exception:
                docs_synced = 0

        indexed_doc_ids = set()
        if user_email and chunks:
            try:
                user_docs = list(files_collection.find({"user_email": user_email}))
                user_doc_ids = set()
                for d in user_docs:
                    fid = d.get("file_id") or d.get("id")
                    if fid:
                        user_doc_ids.add(fid)
                for c in chunks:
                    doc_id = c.get("doc_id")
                    if doc_id:
                        base_doc_id = doc_id.split('_chunk_')[0] if '_chunk_' in doc_id else doc_id
                        if base_doc_id in user_doc_ids:
                            indexed_doc_ids.add(base_doc_id)
            except Exception:
                indexed_doc_ids = set()

        elapsed_seconds = None
        eta_seconds = None
        if progress and progress.get("started_at"):
            elapsed_seconds = round(time.time() - progress["started_at"], 2)
            total_files = progress.get("total_files") or 0
            files_processed = progress.get("files_processed") or 0
            if total_files > 0 and files_processed > 0:
                rate = elapsed_seconds / files_processed
                remaining = max(total_files - files_processed, 0)
                eta_seconds = round(rate * remaining, 2)
                        
        return {
            "vectors": vector_count,
            "faiss_size_kb": round(faiss_size_bytes / 1024, 2),
            "docs_size_kb": round(docs_size_bytes / 1024, 2),
            "docs_count": docs_count,
            "status": processing_status,
            "docs_synced": docs_synced,
            "docs_indexed": len(indexed_doc_ids),
            "total_chunks": len(chunks) if chunks else 0,
            "progress": progress,
            "elapsed_seconds": elapsed_seconds,
            "eta_seconds": eta_seconds
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "vectors": 0,
            "faiss_size_kb": 0,
            "docs_size_kb": 0,
            "docs_count": 0,
            "status": "Error",
            "docs_synced": 0,
            "docs_indexed": 0,
            "total_chunks": 0,
            "progress": None,
            "elapsed_seconds": None,
            "eta_seconds": None
        }
@router.get("/chat/history")
def get_chat_history():
    try:
        from connectors.gdrive import get_drive_service
        try:
            service = get_drive_service()
            about = service.about().get(fields="user").execute()
            user_email = about['user']['emailAddress']
        except Exception:
            # If get_drive_service fails (e.g. not logged in), just return empty
            return {"history": []}
            
        cursor = chats_collection.find({"user_email": user_email})
        # Try to sort, but handle if it's the mock collection which doesn't sort well
        try:
            cursor = cursor.sort("timestamp", 1)
        except Exception:
            pass
        history = []
        for chat in cursor:
            # Format to match frontend Message interface
            msg = {
                "role": chat["role"],
                "content": chat["content"]
            }
            if chat.get("sources"):
                msg["sources"] = chat["sources"]
            history.append(msg)
            
        return {"history": history}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"history": []}

@router.get("/auth/callback")
def auth_callback(state: str, code: str):
    try:
        FRONTEND_URL = os.getenv("FRONTEND_URL", "https://hiighwatch-rag.vercel.app")
        API_URL = os.getenv("API_URL", "https://hiighwatch-rag-3cdc.onrender.com")
        
        import json
        states_file = "oauth_states.json"
        states = {}
        if os.path.exists(states_file):
            with open(states_file, "r") as f:
                try:
                    content = f.read().strip()
                    if content:
                        states = json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"Warning: Failed to parse oauth_states.json in callback: {e}")
                    states = {}
                except Exception as e:
                    print(f"Warning: Error reading oauth_states.json in callback: {e}")
                    pass

        if state not in states:
            # If state is completely missing, redirect to home with error
            return RedirectResponse(url=f"{FRONTEND_URL}/?error=invalid_state")
            
        credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        if not os.path.exists(credentials_path):
            raise Exception(f"OAuth credentials file not found at {credentials_path}. Please download it from Google Cloud Console.")
            
        flow = Flow.from_client_secrets_file(
            credentials_path,
            scopes=SCOPES,
            redirect_uri=f"{API_URL}/auth/callback",
            state=state
        )
        
        # Restore the exact PKCE code_verifier from the JSON file
        flow.code_verifier = states[state]
        
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
        # Clean up the state
        del states[state]
        with open(states_file, "w") as f:
            json.dump(states, f)
            
        # VERY IMPORTANT: If we didn't get a refresh token, and there is an existing token file,
        # we should preserve the old refresh token.
        # But `from_authorized_user_file` and `credentials` handle most of this.
        
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?sync=true")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/chat")
def clear_chat():
    try:
        from connectors.gdrive import get_drive_service
        try:
            service = get_drive_service()
            about = service.about().get(fields="user").execute()
            user_email = about['user']['emailAddress']
        except Exception as e:
            print(f"Error getting user email for clear chat: {e}")
            user_email = "default_user"
            
        result = chats_collection.delete_many({"user_email": user_email})
        deleted_count = result.deleted_count if hasattr(result, 'deleted_count') else 0
        print(f"Cleared {deleted_count} chat messages for user: {user_email}")
        return {"status": "success", "message": f"Chat history cleared. Deleted {deleted_count} messages."}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class AskRequest(BaseModel):
    query: str
    filter_metadata: Optional[Dict[str, str]] = None  # Added for metadata filtering

class Source(BaseModel):
    doc_id: str
    name: str
    chunk_text: str

class AskResponse(BaseModel):
    answer: str
    sources: List[Source]
    cached: bool = False

from db import files_collection, chats_collection
from datetime import datetime

@router.post("/disconnect-drive")
def disconnect_drive_endpoint():
    try:
        token_file = "token.json"
        states_file = "oauth_states.json"
        
        # Remove token.json to force re-authentication
        if os.path.exists(token_file):
            os.remove(token_file)
            
        # Clean up local files
        sync_dir = "synced_docs"
        if os.path.exists(sync_dir):
            for f in os.listdir(sync_dir):
                fp = os.path.join(sync_dir, f)
                if os.path.isfile(fp):
                    os.remove(fp)
            
        # Remove old states
        if os.path.exists(states_file):
            os.remove(states_file)
            
        return {"status": "success", "message": "Successfully disconnected. You can now sync with a new account."}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Keep track of active background syncs
active_syncs = set()
sync_progress = {}

def background_sync_process(items, user_email):
    try:
        active_syncs.add(user_email)
        import time
        import gc
        start_time = time.time()
        sync_progress[user_email] = {
            "started_at": start_time,
            "updated_at": start_time,
            "stage": "downloading",
            "total_files": len(items) if items else 0,
            "files_downloaded": 0,
            "files_processed": 0,
            "chunks_indexed": 0,
            "error": None
        }

        downloaded_files = download_items(items, user_email)
        sync_progress[user_email]["files_downloaded"] = len(downloaded_files)
        sync_progress[user_email]["updated_at"] = time.time()
        if not downloaded_files:
            print("Background: No new files downloaded.")
            sync_progress[user_email]["stage"] = "done"
            sync_progress[user_email]["updated_at"] = time.time()
            return

        try:
            batch_chunks_target = int(os.getenv("EMBED_CHUNK_BATCH", "96"))
        except Exception:
            batch_chunks_target = 96
        batch_chunks_target = max(16, min(batch_chunks_target, 256))

        sync_progress[user_email]["stage"] = "processing"
        sync_progress[user_email]["updated_at"] = time.time()
        index = load_faiss_index()

        pending_chunks = []
        for f in downloaded_files:
            file_chunks = process_single_file(f)
            if file_chunks:
                pending_chunks.extend(file_chunks)
            sync_progress[user_email]["files_processed"] = sync_progress[user_email].get("files_processed", 0) + 1
            sync_progress[user_email]["updated_at"] = time.time()
            gc.collect()

            if len(pending_chunks) >= batch_chunks_target:
                sync_progress[user_email]["stage"] = "embedding"
                sync_progress[user_email]["updated_at"] = time.time()
                embedded_chunks = embed_chunks(pending_chunks)
                sync_progress[user_email]["stage"] = "indexing"
                add_chunks_to_index(index, embedded_chunks)
                sync_progress[user_email]["chunks_indexed"] = sync_progress[user_email].get("chunks_indexed", 0) + len(embedded_chunks)
                sync_progress[user_email]["updated_at"] = time.time()
                pending_chunks = []
                gc.collect()

        if pending_chunks:
            sync_progress[user_email]["stage"] = "embedding"
            sync_progress[user_email]["updated_at"] = time.time()
            embedded_chunks = embed_chunks(pending_chunks)
            sync_progress[user_email]["stage"] = "indexing"
            add_chunks_to_index(index, embedded_chunks)
            sync_progress[user_email]["chunks_indexed"] = sync_progress[user_email].get("chunks_indexed", 0) + len(embedded_chunks)
            sync_progress[user_email]["updated_at"] = time.time()
            pending_chunks = []
            gc.collect()

        sync_progress[user_email]["stage"] = "saving"
        sync_progress[user_email]["updated_at"] = time.time()
        save_faiss_index(index)

        end_time = time.time()
        sync_progress[user_email]["stage"] = "done"
        sync_progress[user_email]["updated_at"] = end_time
        print(f"Background: Sync completed in {round(end_time - start_time, 2)} seconds")
    except Exception as e:
        import traceback
        print("Background Sync Error:")
        traceback.print_exc()
        try:
            import time
            if user_email in sync_progress:
                sync_progress[user_email]["stage"] = "error"
                sync_progress[user_email]["error"] = str(e)
                sync_progress[user_email]["updated_at"] = time.time()
        except Exception:
            pass
    finally:
        active_syncs.discard(user_email)

@router.post("/sync-drive")
def sync_drive_endpoint(background_tasks: BackgroundTasks, force: Optional[bool] = False, folder_url: Optional[str] = None):
    try:
        import time
        start_time = time.time()
        
        if not os.path.exists("token.json"):
            raise Exception("No token.json found. Please login to Google Drive first.")
            
        if force:
            from connectors.gdrive import get_drive_service
            service = get_drive_service()
            try:
                about = service.about().get(fields="user").execute()
                user_email = about['user']['emailAddress']
                files_collection.delete_many({"user_email": user_email})
            except Exception as e:
                print(f"Failed to get user email for force sync: {e}")
                
            # Clear FAISS index as well
            if os.path.exists("synced_docs/faiss.index"):
                os.remove("synced_docs/faiss.index")
            if os.path.exists("synced_docs/chunks.json"):
                os.remove("synced_docs/chunks.json")
            if os.path.exists("synced_docs/chunks.jsonl"):
                os.remove("synced_docs/chunks.jsonl")
                
            # Clear local files
            sync_dir = "synced_docs"
            if os.path.exists(sync_dir):
                for f in os.listdir(sync_dir):
                    fp = os.path.join(sync_dir, f)
                    if os.path.isfile(fp):
                        os.remove(fp)
                
        items, user_email = get_files_to_sync(page_size=20, force=bool(force), folder_url=folder_url)
        if not items:
            return {"status": "success", "files_processed": 0, "message": "No new files to sync.", "files": []}

        end_time = time.time()
        print(f"Sync request accepted in {round(end_time - start_time, 2)} seconds.")

        sync_progress[user_email] = {
            "started_at": time.time(),
            "updated_at": time.time(),
            "stage": "queued",
            "total_files": len(items),
            "files_downloaded": 0,
            "files_processed": 0,
            "chunks_indexed": 0
        }
        background_tasks.add_task(background_sync_process, items, user_email)

        return {
            "status": "success",
            "files_processed": len(items),
            "message": f"Sync started for {len(items)} files. Indexing is running in the background.",
            "files": [{"id": f["id"], "name": f["name"]} for f in items]
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = str(e)
        if "Google Drive API has not been used" in error_msg:
            error_msg = "Google Drive API is not enabled. Visit https://console.cloud.google.com/apis/library/drive.googleapis.com to enable it."
        # If we hit an out of memory error, throw a clear exception
        if "killed" in error_msg.lower() or "memory" in error_msg.lower():
            error_msg = "The server ran out of memory while processing your PDFs. Try syncing fewer or smaller files."
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest):
    try:
        from connectors.gdrive import get_drive_service
        try:
            service = get_drive_service()
            about = service.about().get(fields="user").execute()
            user_email = about['user']['emailAddress']
        except Exception:
            user_email = "default_user"

        progress = sync_progress.get(user_email) if user_email else None
        if (user_email in active_syncs) or (progress and progress.get("stage") not in (None, "done", "error")):
            return AskResponse(
                answer="Your documents are still syncing and being indexed. Please wait for Index Stats to show Ready, then try again.",
                sources=[],
                cached=False
            )

        # Save user query to MongoDB
        chats_collection.insert_one({
            "user_email": user_email,
            "role": "user",
            "content": req.query,
            "timestamp": datetime.utcnow()
        })

        # Cache key based on query and filters
        cache_key = hashlib.md5(f"{req.query}_{req.filter_metadata}".encode()).hexdigest()
        
        is_summary_request = req.query.startswith("Please provide a comprehensive summary of the document: ")

        # Auto-detect summary requests to apply metadata filtering
        filter_metadata = req.filter_metadata
        faiss_query = req.query
        if is_summary_request:
            doc_name = req.query.replace("Please provide a comprehensive summary of the document: ", "").strip()
            if not filter_metadata:
                doc = files_collection.find_one({"user_email": user_email, "name": doc_name})
                if not doc:
                    try:
                        import re
                        doc = files_collection.find_one({"user_email": user_email, "name": {"$regex": f"^{re.escape(doc_name)}$", "$options": "i"}})
                    except Exception:
                        doc = None

                if not doc:
                    try:
                        import re
                        doc = files_collection.find_one({"user_email": user_email, "name": {"$regex": re.escape(doc_name), "$options": "i"}})
                    except Exception:
                        doc = None

                if doc and doc.get("file_id"):
                    filter_metadata = {"doc_id": doc["file_id"]}
                else:
                    filter_metadata = {"name": doc_name}

            faiss_query = f"Overview and summary of {doc_name}"
                
        top_k = 12 if is_summary_request else 8

        top_chunks = search_faiss(faiss_query, k=top_k, filters=filter_metadata)
        
        if not top_chunks:
            if is_summary_request:
                try:
                    doc_name = req.query.replace("Please provide a comprehensive summary of the document: ", "").strip()
                    doc = files_collection.find_one({"user_email": user_email, "name": doc_name})
                    if doc:
                        return AskResponse(
                            answer="That document is synced but not indexed yet. Please wait for Index Stats to show Ready (and the document status to show Indexed), then try again.",
                            sources=[],
                            cached=False
                        )
                except Exception:
                    pass
            return AskResponse(
                answer="I couldn't find any relevant information in your synced documents.",
                sources=[],
                cached=False
            )

        # 2. Format context for the LLM
        context_parts = []
        sources = []
        for chunk in top_chunks:
            doc_id = chunk["doc_id"]
            text = chunk["text"]
            metadata = get_document_metadata(doc_id)
            doc_name = metadata.get("name", "Unknown Document") if metadata else "Unknown Document"
            
            context_parts.append(f"Document: {doc_name}\nContent:\n{text}")
            
            # Avoid duplicate sources in the output list if they have the same doc_id
            if not any(s.doc_id == doc_id for s in sources):
                sources.append(Source(doc_id=doc_id, name=doc_name, chunk_text=text))

        context_block = "\n\n---\n\n".join(context_parts)
        
        # Build chat history for Groq
        cursor = chats_collection.find({"user_email": user_email})
        try:
            cursor = cursor.sort("timestamp", 1)
        except Exception:
            pass
        chat_history_list = list(cursor)[-6:]
        
        system_prompt = """You are Highwatch, an advanced, highly intelligent conversational AI assistant (similar to ChatGPT) integrated directly into the user's Google Drive. 
Your primary goal is to help the user understand, analyze, and extract insights from their synced documents.

Rules:
1. Act naturally conversational, helpful, and highly articulate.
2. When answering questions, prioritize using the provided 'Context' (which contains text extracted from their Drive files).
3. If the answer is in the Context, synthesize it beautifully and clearly.
4. If the user asks a follow-up question or makes a conversational remark, use the conversation history to respond intelligently.
5. If you truly do not know the answer based on the Context or History, politely explain that you cannot find that information in their currently synced Drive files, but offer to help with something else. DO NOT hallucinate facts about their documents.
6. Use markdown formatting (bolding, bullet points, etc.) to make your answers easy to read."""

        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add history
        for chat in chat_history_list:
            role = "user" if chat["role"] == "user" else "assistant"
            # Don't include the current query in the history loop since we'll add it below
            if chat["content"] != req.query:
                messages.append({"role": role, "content": chat["content"]})

        # Add the current prompt with context
        prompt_with_context = f"""Context:
{context_block}

Question:
{req.query}"""

        messages.append({"role": "user", "content": prompt_with_context})

        # 3. Query Groq API
        if not os.getenv("GROQ_API_KEY"):
            raise Exception("GROQ_API_KEY is not set in environment variables.")
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        max_tokens = 1024 if is_summary_request else 768

        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4,
                max_tokens=max_tokens,
            )
            answer = completion.choices[0].message.content
        except Exception as e:
            if "rate_limit_exceeded" in str(e).lower() or "429" in str(e):
                raise Exception("The AI rate limit has been reached for today. Please wait a while or upgrade your API key to continue chatting.")
            else:
                raise e
        
        # Save to cache
        llm_cache[cache_key] = {
            "answer": answer,
            "sources": sources
        }

        # Save AI response to MongoDB
        chats_collection.insert_one({
            "user_email": user_email,
            "role": "ai",
            "content": answer,
            "sources": [s.dict() for s in sources],
            "timestamp": datetime.utcnow()
        })

        return AskResponse(answer=answer, sources=sources, cached=False)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class AnalyticsResponse(BaseModel):
    answer: str
    sources: List[Source]
    active_claws: List[str]
    cached: bool = False

@router.post("/analytics/orchestrate", response_model=AnalyticsResponse)
def orchestrate_endpoint(req: AskRequest):
    try:
        from connectors.gdrive import get_drive_service
        try:
            service = get_drive_service()
            about = service.about().get(fields="user").execute()
            user_email = about['user']['emailAddress']
        except Exception:
            user_email = "default_user"

        progress = sync_progress.get(user_email) if user_email else None
        if (user_email in active_syncs) or (progress and progress.get("stage") not in (None, "done", "error")):
            return AnalyticsResponse(
                answer="Your documents are still syncing and being indexed. Please wait for Index Stats to show Ready, then try again.",
                sources=[],
                active_claws=[],
                cached=False
            )

        # Save user query to MongoDB
        chats_collection.insert_one({
            "user_email": user_email,
            "role": "user",
            "content": req.query,
            "timestamp": datetime.utcnow()
        })

        # Cache key based on query and filters
        cache_key = hashlib.md5(f"orchestrate_{req.query}_{req.filter_metadata}".encode()).hexdigest()
        if cache_key in llm_cache:
            cached_data = llm_cache[cache_key]
            # Save AI response to MongoDB
            chats_collection.insert_one({
                "user_email": user_email,
                "role": "ai",
                "content": cached_data["answer"],
                "sources": [s.dict() for s in cached_data["sources"]],
                "timestamp": datetime.utcnow()
            })
            return AnalyticsResponse(
                answer=cached_data["answer"],
                sources=cached_data["sources"],
                active_claws=cached_data["active_claws"],
                cached=True
            )

        from analytics.orchestrator import MasterOrchestrator
        orchestrator = MasterOrchestrator()
        result = orchestrator.run_pipeline(req.query, filter_metadata=req.filter_metadata)

        response_sources = []
        for src in result["sources"]:
            response_sources.append(Source(
                doc_id=src["doc_id"],
                name=src["name"],
                chunk_text=src["chunk_text"]
            ))

        # Save to cache
        llm_cache[cache_key] = {
            "answer": result["answer"],
            "sources": response_sources,
            "active_claws": result["active_claws"]
        }

        # Save AI response to MongoDB
        chats_collection.insert_one({
            "user_email": user_email,
            "role": "ai",
            "content": result["answer"],
            "sources": [s.dict() for s in response_sources],
            "timestamp": datetime.utcnow()
        })

        return AnalyticsResponse(
            answer=result["answer"],
            sources=response_sources,
            active_claws=result["active_claws"],
            cached=False
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
