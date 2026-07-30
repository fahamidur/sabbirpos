from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import uvicorn

# ---------------- CONFIG ----------------
HOST = "0.0.0.0"
PORT = 8000
# ---------------------------------------

app = FastAPI(title="MT5 Candle API")

class Candle(BaseModel):
    symbol: str
    timeframe: str
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: int

@app.post("/candle")
async def receive_candle(candle: Candle):
    readable_time = datetime.utcfromtimestamp(candle.time)
    print(
        f"Received {candle.symbol} "
        f"{candle.timeframe} "
        f"{readable_time} "
        f"O:{candle.open} H:{candle.high} "
        f"L:{candle.low} C:{candle.close}"
    )
    return {"status": "ok"}

# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False
    )
