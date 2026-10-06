from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Usage Billing Engine API is running"}