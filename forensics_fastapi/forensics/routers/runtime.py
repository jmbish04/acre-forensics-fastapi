import asyncio
import sys
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Runtime"])

class RunRequest(BaseModel):
    args: List[str]

@router.post("/run/{module}", operation_id="run_python_module")
async def run_module(module: str, request: RunRequest):
    """
    Execute a python module with arguments.
    Mimics 'python -m module ...args'
    """
    try:
        # Construct command: python3 -m <module> <args>
        cmd = [sys.executable, "-m", module] + request.args
        
        # Log command
        print(f"Executing: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await proc.communicate()
        
        exit_code = proc.returncode or 0
        
        # Try to parse stdout as JSON if possible, or return as string
        out_str = stdout.decode().strip()
        err_str = stderr.decode().strip()
        
        return {
            "stdout": out_str,
            "stderr": err_str,
            "exitCode": exit_code
        }
        
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exitCode": 1
        }
