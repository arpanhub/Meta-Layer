"""
Meta-Layer Gateway Service
Acts as middleware between agents and the Tool Warehouse
"""
import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="ADK Meta-Layer Gateway",
    version="1.0.0",
    description="Middleware gateway routing agent requests to Tool Warehouse"
)

# Configuration
TOOL_WAREHOUSE_URL = os.getenv("TOOL_WAREHOUSE_URL", "http://localhost:8001")

# Pydantic Models
class ToolExecutionRequest(BaseModel):
    parameters: Dict[str, Any] = {}

class ToolExecutionResponse(BaseModel):
    success: bool
    tool_name: str
    result: Any = None
    error: Optional[str] = None

# ============================================================================
# HEALTH & STATUS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "meta-layer-gateway",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "health": "/health",
            "discover_tools": "/tools",
            "execute_tool": "/execute/{tool_name}"
        },
        "connected_to": TOOL_WAREHOUSE_URL
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Also verifies connection to Tool Warehouse.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TOOL_WAREHOUSE_URL}/health", timeout=5.0)
            warehouse_healthy = response.status_code == 200
    except:
        warehouse_healthy = False
    
    return {
        "status": "healthy" if warehouse_healthy else "degraded",
        "service": "meta-layer-gateway",
        "version": "1.0.0",
        "tool_warehouse": {
            "url": TOOL_WAREHOUSE_URL,
            "status": "connected" if warehouse_healthy else "unreachable"
        }
    }

# ============================================================================
# DISCOVERY (Used by Meta-Agent)
# ============================================================================

@app.get("/tools")
async def discover_tools():
    """
    Returns available tools from Tool Warehouse.
    Used by Meta-Agent to generate Newborn Agent stubs.
    
    Returns:
        Registry JSON with all available tools
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TOOL_WAREHOUSE_URL}/tools", timeout=10.0)
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Tool Warehouse returned error: {response.text}"
                )
    
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Tool Warehouse timeout - service may be unavailable"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach Tool Warehouse at {TOOL_WAREHOUSE_URL}: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Meta-Layer error: {str(e)}"
        )

@app.get("/registry")
async def get_registry():
    """Alias for /tools endpoint."""
    return await discover_tools()

# ============================================================================
# EXECUTION (Used by Newborn Agents)
# ============================================================================

@app.post("/execute/{tool_name}", response_model=ToolExecutionResponse)
async def execute_tool(tool_name: str, request: ToolExecutionRequest):
    """
    Execute a tool via Tool Warehouse.
    Used by Newborn Agents to run tools without containing the logic.
    
    Args:
        tool_name: Name of tool to execute
        request: Parameters for the tool
    
    Returns:
        ToolExecutionResponse with result or error
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TOOL_WAREHOUSE_URL}/execute/{tool_name}",
                json={"parameters": request.parameters},
                timeout=30.0  # Longer timeout for tool execution
            )
            
            if response.status_code == 200:
                result = response.json()
                return ToolExecutionResponse(**result)
            else:
                error_detail = response.json().get("detail", response.text)
                return ToolExecutionResponse(
                    success=False,
                    tool_name=tool_name,
                    error=f"Tool Warehouse error: {error_detail}"
                )
    
    except httpx.TimeoutException:
        return ToolExecutionResponse(
            success=False,
            tool_name=tool_name,
            error="Tool execution timeout - tool may be taking too long"
        )
    except httpx.RequestError as e:
        return ToolExecutionResponse(
            success=False,
            tool_name=tool_name,
            error=f"Cannot reach Tool Warehouse: {str(e)}"
        )
    except Exception as e:
        return ToolExecutionResponse(
            success=False,
            tool_name=tool_name,
            error=f"Meta-Layer error: {str(e)}"
        )

# ============================================================================
# TOOL CODE RETRIEVAL (Optional - for debugging)
# ============================================================================

@app.get("/tools/{tool_name}/code")
async def get_tool_code(tool_name: str):
    """
    Retrieves source code for a tool (debugging/reference).
    Proxies to Tool Warehouse.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TOOL_WAREHOUSE_URL}/tools/{tool_name}/code",
                timeout=10.0
            )
            
            if response.status_code == 200:
                return {"tool_name": tool_name, "code": response.text}
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving tool code: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)