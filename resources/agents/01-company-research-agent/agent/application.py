import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.graph import Graph
from backend.services.mongodb import MongoDBService
from backend.services.pdf_service import PDFService
from backend.classes.state import job_status

# Load environment variables from .env file at startup
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
logger.addHandler(console_handler)

app = FastAPI(title="Tavily Company Research API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
pdf_service = PDFService({"pdf_output_dir": "pdfs"})

mongodb = None
if mongo_uri := os.getenv("MONGODB_URI"):
    try:
        mongodb = MongoDBService(mongo_uri)
        logger.info("MongoDB integration enabled")
    except Exception as e:
        logger.warning(f"Failed to initialize MongoDB: {e}. Continuing without persistence.")

class ResearchRequest(BaseModel):
    company: str
    company_url: str | None = None
    industry: str | None = None
    hq_location: str | None = None

class PDFGenerationRequest(BaseModel):
    report_content: str
    company_name: str | None = None

@app.options("/research")
async def preflight():
    response = JSONResponse(content=None, status_code=200)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.post("/research")
async def research(data: ResearchRequest):
    try:
        logger.info(f"Received research request for {data.company}")
        job_id = str(uuid.uuid4())
        asyncio.create_task(process_research(job_id, data))

        response = JSONResponse(content={
            "status": "accepted",
            "job_id": job_id,
            "message": "Research started. Connect to /research/{job_id}/stream for updates."
        })
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    except Exception as e:
        logger.error(f"Error initiating research: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def process_research(job_id: str, data: ResearchRequest):
    """Process research request asynchronously and store results"""
    try:
        if mongodb:
            mongodb.create_job(job_id, data.dict())
        
        await asyncio.sleep(0.5)  # Brief delay
        
        logger.info(f"Starting research for {data.company}")

        graph = Graph(
            company=data.company,
            url=data.company_url,
            industry=data.industry,
            hq_location=data.hq_location,
            job_id=job_id
        )

        final_state = {}
        
        # Stream through the graph and update progress
        async for state in graph.run(thread={}):
            final_state.update(state)
            node_name = list(state.keys())[0] if state else 'unknown'
            logger.debug(f"Node completed: {node_name}")
            
            # Update job status with current step
            job_status[job_id].update({
                "status": "processing",
                "current_step": node_name,
                "last_update": datetime.now().isoformat()
            })
        
        # Extract final report
        report_content = final_state.get('report') or (final_state.get('editor') or {}).get('report')
        
        if report_content:
            logger.info(f"Research completed. Report length: {len(report_content)}")
            
            job_status[job_id].update({
                "status": "completed",
                "report": report_content,
                "company": data.company,
                "last_update": datetime.now().isoformat()
            })
            
            if mongodb:
                mongodb.update_job(job_id=job_id, status="completed")
                mongodb.store_report(job_id=job_id, report_data={"report": report_content})
            
            logger.info(f"Research completed successfully for {data.company}")
        else:
            logger.error(f"Research completed without report. State keys: {list(final_state.keys())}")
            job_status[job_id].update({
                "status": "failed",
                "error": "No report generated",
                "last_update": datetime.now().isoformat()
            })

    except Exception as e:
        logger.error(f"Research failed: {str(e)}", exc_info=True)
        job_status[job_id].update({
            "status": "failed",
            "error": str(e),
            "last_update": datetime.now().isoformat()
        })
        
        if mongodb:
            mongodb.update_job(job_id=job_id, status="failed", error=str(e))

@app.get("/")
async def ping():
    return {"message": "Alive"}

@app.get("/research/pdf/{filename}")
async def get_pdf(filename: str):
    pdf_path = os.path.join("pdfs", filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type='application/pdf', filename=filename)

@app.get("/research/{job_id}")
async def get_research(job_id: str):
    if not mongodb:
        raise HTTPException(status_code=501, detail="Database persistence not configured")
    job = mongodb.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job

@app.get("/research/{job_id}/stream")
async def stream_research(job_id: str):
    """Stream research progress via SSE"""
    async def event_generator():
        try:
            # Wait for job to exist
            for _ in range(50):
                if job_id in job_status:
                    break
                await asyncio.sleep(0.1)
            
            last_step = None
            
            # Stream status updates
            while job_id in job_status:
                result = job_status[job_id]
                status = result.get("status")
                current_step = result.get("current_step")
                events = result.get("events", [])
                
                # Send node progress updates when step changes
                if status == "processing" and current_step and current_step != last_step:
                    data = json.dumps({"type": "progress", "step": current_step})
                    yield f"data: {data}\n\n"
                    last_step = current_step
                
                # Send all queued events (FIFO - pop from start)
                while events:
                    event = events.pop(0)
                    data = json.dumps(event)
                    yield f"data: {data}\n\n"
                
                if status == "completed" and (report := result.get("report")):
                    data = json.dumps({"type": "complete", "report": report})
                    yield f"data: {data}\n\n"
                    break
                elif status == "failed":
                    data = json.dumps({"type": "error", "error": result.get("error", "Unknown error")})
                    yield f"data: {data}\n\n"
                    break
                
                await asyncio.sleep(0.1)  # Faster polling for responsive updates
        except Exception as e:
            data = json.dumps({"type": "error", "error": str(e)})
            yield f"data: {data}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/research/{job_id}/report")
async def get_research_report(job_id: str):
    if not mongodb:
        if job_id in job_status:
            result = job_status[job_id]
            if report := result.get("report"):
                return {"report": report}
            # Job exists but report not ready yet
            return JSONResponse(
                status_code=202,
                content={"status": result.get("status", "pending"), "message": "Report not ready yet"}
            )
        raise HTTPException(status_code=404, detail="Job not found")
    
    report = mongodb.get_report(job_id)
    if not report:
        # Check if job exists
        if job := mongodb.get_job(job_id):
            return JSONResponse(
                status_code=202,
                content={"status": job.get("status", "pending"), "message": "Report not ready yet"}
            )
        raise HTTPException(status_code=404, detail="Job not found")
    return report

@app.post("/generate-pdf")
async def generate_pdf(data: PDFGenerationRequest):
    """Generate a PDF from markdown content and stream it to the client."""
    try:
        success, result = pdf_service.generate_pdf_stream(data.report_content, data.company_name)
        if success:
            pdf_buffer, filename = result
            return StreamingResponse(
                pdf_buffer,
                media_type='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )
        else:
            raise HTTPException(status_code=500, detail=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
