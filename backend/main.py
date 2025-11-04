from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List
import asyncio
import random
import time

app = FastAPI()

# In-memory storage for KPIs and their data
kpis: Dict[str, Dict] = {}
kpi_feeds: Dict[str, List[WebSocket]] = {}

@app.post("/kpis")
async def create_kpi(kpi_data: Dict):
    """
    Create a new KPI, assign it a ticker, and store its metadata.
    This would trigger an on-chain transaction to the KPIRegistry.
    """
    # In a real system, the ticker would be derived more robustly.
    ticker = kpi_data.get("name", "KPI")[:4].upper() + str(len(kpis) + 1).zfill(2)
    kpis[ticker] = {
        "name": kpi_data.get("name"),
        "description": kpi_data.get("description"),
        "formula": kpi_data.get("formula"),
        "last_value": None,
        "ticker": ticker
    }
    kpi_feeds[ticker] = []
    print(f"KPI Created: {ticker} - {kpi_data.get('name')}")
    # TODO: Interact with KPIRegistry.sol to deploy the token and oracle
    return {"status": "created", "ticker": ticker, "kpi_info": kpis[ticker]}

@app.get("/kpis")
async def get_kpis():
    """List all currently active KPIs."""
    return {"kpis": list(kpis.values())}

@app.post("/appraise")
async def appraise_prompt(prompt_data: Dict):
    """
    Appraise a prompt against all active KPIs.
    This uses a placeholder LLM logic to generate scores.
    """
    prompt_text = prompt_data.get("text", "")
    scores = {}

    # Placeholder for LLM-based appraisal
    for ticker in kpis:
        # Simulate a score based on the length of the prompt and KPI name
        score = (len(prompt_text) * len(kpis[ticker]['name'])) % 100 / 100.0
        scores[ticker] = score

    # TODO: Interact with the AppraisalRouter contract to mint/reward tokens
    return {"prompt_text": prompt_text, "dominance_scores": scores}

@app.websocket("/ws/kpi/{ticker}")
async def websocket_endpoint(websocket: WebSocket, ticker: str):
    """WebSocket endpoint to stream live updates for a specific KPI."""
    if ticker not in kpi_feeds:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    kpi_feeds[ticker].append(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep the connection alive
    except WebSocketDisconnect:
        kpi_feeds[ticker].remove(websocket)

async def broadcast_kpi_updates():
    """
    A background task that simulates KPI value updates and broadcasts
    them to connected WebSocket clients.
    """
    while True:
        await asyncio.sleep(5) # Update every 5 seconds
        for ticker, kpi_data in kpis.items():
            # Simulate a random value update
            new_value = random.uniform(0, 100)
            kpi_data["last_value"] = new_value

            # TODO: This is where the off-chain oracle would sign the value
            # and submit it to the KPIOracle.sol contract.

            update_message = {
                "ticker": ticker,
                "timestamp": int(time.time()),
                "value": new_value
            }

            # Broadcast to all subscribed clients
            for websocket in kpi_feeds.get(ticker, []):
                await websocket.send_json(update_message)

@app.on_event("startup")
async def startup_event():
    """Start the background task when the server starts."""
    asyncio.create_task(broadcast_kpi_updates())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
