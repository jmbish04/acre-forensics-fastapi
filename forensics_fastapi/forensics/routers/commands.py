import asyncio
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/commands", tags=["Commands"])


class ExecRequest(BaseModel):
    command: str
    args: List[str] = []


class ExecPythonRequest(BaseModel):
    code: str


class ExecResponse(BaseModel):
    stdout: str
    stderr: str
    exitCode: int


@router.post("/exec", response_model=ExecResponse, operation_id="exec_command")
async def exec_command(request: ExecRequest):
    """
    Execute a shell command within the container asynchronously.
    """
    try:
        # Construct command
        if not request.command:
            raise HTTPException(status_code=400, detail="Missing 'command'")

        cmd = [request.command] + request.args

        # Async execution
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        return ExecResponse(
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
            exitCode=proc.returncode or 0,
        )
    except FileNotFoundError:
        return ExecResponse(stdout="", stderr=f"Command not found: {request.command}", exitCode=127)
    except Exception as e:
        return ExecResponse(stdout="", stderr=str(e), exitCode=1)


@router.post("/exec-python", response_model=ExecResponse, operation_id="exec_python")
async def exec_python(request: ExecPythonRequest):
    """
    Execute Python code directly using python3 -c asynchronously.
    """
    try:
        if not request.code:
            raise HTTPException(status_code=400, detail="Missing 'code'")

        proc = await asyncio.create_subprocess_exec(
            "python3",
            "-c",
            request.code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        return ExecResponse(
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
            exitCode=proc.returncode or 0,
        )
    except Exception as e:
        return ExecResponse(stdout="", stderr=str(e), exitCode=1)
