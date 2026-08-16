from fastapi import FastAPI, HTTPException
import json


app = FastAPI()


@app.get("/")
def root():
    return {"message": "Server API", "status": "OK"}


@app.get("/api/whs")
def title():
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return {"title_suffix": json.load(f).get("title_suffix", {})}
    except:
        return {"title_suffix": {}}
