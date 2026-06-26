import os
import json
import sqlite3
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.agent import app as claims_app

app = FastAPI(title="Claims Adjuster Dashboard")

# Ensure static dir exists
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/api/pending")
def get_pending_claims():
    """Reads the ADK SQLite session DB to find paused sessions."""
    db_path = "app/.adk/session.db"
    if not os.path.exists(db_path):
        return {"pending_claims": []}
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, state FROM sessions").fetchall()
        pending = []
        for row in rows:
            session_id = row['id']
            try:
                # Check the last event to see if it is waiting for input
                last_event_row = conn.execute("SELECT event_data FROM events WHERE session_id=? ORDER BY timestamp DESC LIMIT 1", (session_id,)).fetchone()
                if not last_event_row:
                    continue
                
                event_json = json.loads(last_event_row['event_data'])
                if not event_json.get("long_running_tool_ids"):
                    continue # Not paused
                
                state_data = json.loads(row['state'])
                
                pending.append({
                    "session_id": session_id,
                    "policy_id": state_data.get("policy_id", "Unknown"),
                    "hospital": state_data.get("hospital", "Unknown"),
                    "treatment": state_data.get("treatment", "Unknown"),
                    "cost": state_data.get("estimated_cost", 0.0),
                    "risk_data": state_data.get("risk_data", {}),
                    "paused_node": "human_approval"
                })
            except Exception as e:
                print(f"Error parsing session {session_id}: {e}")
                
        return {"pending_claims": pending}
    finally:
        conn.close()

class ActionRequest(BaseModel):
    decision: str
    notes: str = ""

@app.post("/api/action/{session_id}")
async def take_action(session_id: str, action: ActionRequest):
    """Resumes the ADK workflow for a given session by sending a POST request to the ADK agent server."""
    try:
        print(f"Resuming session {session_id} with decision {action.decision}")
        
        payload = {
            "appName": "app",
            "userId": "user",
            "sessionId": session_id,
            "newMessage": {
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "id": "decision_input",
                        "name": "adk_request_input",
                        "response": {
                            "decision": action.decision,
                            "user_notes": action.notes
                        }
                    }
                }]
            }
        }
        
        import urllib.request
        import json
        req = urllib.request.Request(
            "http://127.0.0.1:8080/run", 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                result = response.read().decode('utf-8')
                print(f"ADK Server response: {result}")
        except Exception as api_err:
            print(f"ADK Server returned an error: {api_err.read().decode('utf-8') if hasattr(api_err, 'read') else str(api_err)}")
            raise api_err
            
        return {"status": "success", "message": f"Session {session_id} resumed."}
    except Exception as e:
        print(f"Error resuming session: {e}")
        raise HTTPException(status_code=500, detail=str(e))
