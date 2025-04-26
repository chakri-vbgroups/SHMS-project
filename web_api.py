from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from pymongo import MongoClient
import paho.mqtt.publish as publish
import json
from typing import List, Optional
from collections import defaultdict
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

# --- FastAPI App and Config ---
app = FastAPI()

# --- OAuth2 & Security Setup ---
SECRET_KEY = "key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Fake User DB for demo (can be replaced with a real DB) ---
fake_users_db = {
    "testuser": {
        "username": "testuser",
        "full_name": "Test User",
        "email": "test@example.com",
        "hashed_password": pwd_context.hash("password123"),  # Hash the password once!
        "disabled": False
    }
}

# --- MongoDB setup ---
mongo_client = MongoClient("mongodb://localhost:27017/")
mongo_db = mongo_client["demo"]
mongo_collection = mongo_db["machine_metrics"]

# MQTT Setup
mqtt_broker = "test.mosquitto.org"
data_topic = "trail_me"

# --- Models ---
class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

class MachineData(BaseModel):
    machine_id: str
    timestamp: str
    temperature: float
    vibration: float
    rpm: int

# --- Helper Functions ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db, username: str) -> Optional[UserInDB]:
    if username in db:
        return UserInDB(**db[username])

def authenticate_user(username: str, password: str):
    user = get_user(fake_users_db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Routes ---
@app.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# Secured Endpoint
@app.get("/protected")
async def get_protected_data(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = get_user(fake_users_db, username)
        if not user or user.disabled:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        return {"message": f"Welcome {user.username}! your are Protected"}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# --- POST Endpoint to Send Data (Secured) ---
@app.post("/send_data/")
def send_data(data: MachineData, token: str = Depends(oauth2_scheme)):
    try:
        # Decode the token to get the user information
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = get_user(fake_users_db, username)

        # Publish to MQTT
        json_data = json.dumps(data.dict())
        publish.single(topic=data_topic, payload=json_data, hostname=mqtt_broker)

        # Store in MongoDB if temperature is out of safe range
        if data.temperature > 90 or data.temperature < 70:
            mongo_collection.insert_one(data.dict())

        return {"message": "Data sent to MQTT broker and stored if alert triggered."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/send_data_batch/")
def send_data_batch(data_list: List[MachineData], token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = get_user(fake_users_db, username)

        for data in data_list:
            json_data = json.dumps(data.dict())
            publish.single(topic=data_topic, payload=json_data, hostname=mqtt_broker)

            if data.temperature > 90 or data.temperature < 70:
                mongo_collection.insert_one(data.dict())

        return {"message": "All data sent and alerts stored if needed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


# GET for individual data of machine and all data (Secured)
@app.get("/alerts/", response_model=List[dict])
def get_alerts(machine_id: Optional[str] = None, token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = get_user(fake_users_db, username)

        query = {"machine_id": machine_id} if machine_id else {}
        alerts = list(mongo_collection.find(query, {"_id": 0}))
        return alerts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Additional Protected Routes (as needed) ---
@app.get("/metrics/latest/")
def get_latest_metrics(machine_id: str, limit: int = 10, token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = get_user(fake_users_db, username)

        query = {"machine_id": machine_id}
        cursor = mongo_collection.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
        data = list(cursor)
        return data[::-1]  # Return oldest to newest
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# GET for all historical metrics for a machine (Secured)
@app.get("/metrics/history/")
def get_all_metrics(machine_id: str, token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = get_user(fake_users_db, username)

        query = {"machine_id": machine_id}
        cursor = mongo_collection.find(query, {"_id": 0}).sort("timestamp", 1)
        return list(cursor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
