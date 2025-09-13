from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from typing import Optional, List
import os
from bson import ObjectId
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Pydantic models
class ComplaintCreate(BaseModel):
    hostel: str
    room: str
    type: str
    description: str

class ComplaintUpdate(BaseModel):
    status: str

class Complaint(BaseModel):
    id: int
    hostel: str
    room: str
    type: str
    description: str
    status: str
    submitted: int  # timestamp
    resolved: Optional[int] = None  # timestamp

class ComplaintResponse(BaseModel):
    id: int
    hostel: str
    room: str
    type: str
    description: str
    status: str
    submitted: int
    resolved: Optional[int] = None

class StatsResponse(BaseModel):
    total: int
    open: int
    resolved: int
    avgResolution: float

# Initialize FastAPI app
app = FastAPI(title="Hostel Complaint Management API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
# Replace with your actual MongoDB Atlas connection string
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb+srv://yourusername:yourpassword@cluster0.abc123.mongodb.net/hostel_management?retryWrites=true&w=majority")
DATABASE_NAME = "hostel_management"
COLLECTION_NAME = "complaints"

client = AsyncIOMotorClient(MONGODB_URL)
database = client[DATABASE_NAME]
collection = database[COLLECTION_NAME]

# Helper functions
async def get_next_complaint_id():
    """Get the next sequential complaint ID"""
    last_complaint = await collection.find_one(sort=[("id", -1)])
    if last_complaint:
        return last_complaint["id"] + 1
    return 1

def complaint_helper(complaint) -> dict:
    """Convert MongoDB document to dictionary"""
    return {
        "id": complaint["id"],
        "hostel": complaint["hostel"],
        "room": complaint["room"],
        "type": complaint["type"],
        "description": complaint["description"],
        "status": complaint["status"],
        "submitted": complaint["submitted"],
        "resolved": complaint.get("resolved")
    }

# API Routes

@app.get("/")
async def root():
    return {"message": "Hostel Complaint Management API"}

@app.get("/api/complaints", response_model=List[ComplaintResponse])
async def get_all_complaints():
    """Get all complaints"""
    try:
        complaints = []
        async for complaint in collection.find():
            complaints.append(complaint_helper(complaint))
        return complaints
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/complaints/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(complaint_id: int):
    """Get a specific complaint by ID"""
    try:
        complaint = await collection.find_one({"id": complaint_id})
        if complaint:
            return complaint_helper(complaint)
        raise HTTPException(status_code=404, detail="Complaint not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/complaints", response_model=ComplaintResponse)
async def create_complaint(complaint: ComplaintCreate):
    """Create a new complaint"""
    try:
        complaint_id = await get_next_complaint_id()
        current_time = int(datetime.now().timestamp() * 1000)  # milliseconds
        
        complaint_doc = {
            "id": complaint_id,
            "hostel": complaint.hostel,
            "room": complaint.room,
            "type": complaint.type,
            "description": complaint.description,
            "status": "Pending",
            "submitted": current_time,
            "resolved": None
        }
        
        result = await collection.insert_one(complaint_doc)
        if result.inserted_id:
            return complaint_helper(complaint_doc)
        raise HTTPException(status_code=500, detail="Failed to create complaint")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/complaints/{complaint_id}", response_model=ComplaintResponse)
async def update_complaint_status(complaint_id: int, update: ComplaintUpdate):
    """Update complaint status"""
    try:
        update_data = {"status": update.status}
        
        # If status is being set to Resolved, add resolved timestamp
        if update.status == "Resolved":
            update_data["resolved"] = int(datetime.now().timestamp() * 1000)
        elif update.status != "Resolved":
            # If changing from Resolved to another status, remove resolved timestamp
            update_data["resolved"] = None
        
        result = await collection.update_one(
            {"id": complaint_id},
            {"$set": update_data}
        )
        
        if result.modified_count:
            updated_complaint = await collection.find_one({"id": complaint_id})
            return complaint_helper(updated_complaint)
        raise HTTPException(status_code=404, detail="Complaint not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/complaints/{complaint_id}")
async def delete_complaint(complaint_id: int):
    """Delete a complaint"""
    try:
        result = await collection.delete_one({"id": complaint_id})
        if result.deleted_count:
            return {"message": "Complaint deleted successfully"}
        raise HTTPException(status_code=404, detail="Complaint not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/complaints/stats/dashboard", response_model=StatsResponse)
async def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        # Get all complaints
        all_complaints = []
        async for complaint in collection.find():
            all_complaints.append(complaint)
        
        total = len(all_complaints)
        resolved_complaints = [c for c in all_complaints if c["status"] == "Resolved"]
        resolved_count = len(resolved_complaints)
        open_count = total - resolved_count
        
        # Calculate average resolution time
        avg_resolution = 0.0
        if resolved_complaints:
            total_time = 0
            for complaint in resolved_complaints:
                if complaint.get("resolved") and complaint.get("submitted"):
                    resolution_time = complaint["resolved"] - complaint["submitted"]
                    total_time += resolution_time
            
            if total_time > 0:
                avg_resolution = (total_time / len(resolved_complaints)) / 3600000  # Convert to hours
        
        return StatsResponse(
            total=total,
            open=open_count,
            resolved=resolved_count,
            avgResolution=round(avg_resolution, 1)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hostels")
async def get_hostels():
    """Get list of available hostels"""
    return {
        "hostels": ["JAH", "IBADAN", "LAGOS", "PREMIUM", "DLW", "UMH", "UFH"]
    }

@app.get("/api/complaint-types")
async def get_complaint_types():
    """Get list of complaint types"""
    return {
        "types": ["Plumbing", "Electrical", "Maintenance", "Cleaning", "Security", "Other"]
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        await client.admin.command('ping')
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database connection failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)