import asyncio
import os
import platform
import subprocess
import sys
from typing import Any, Dict, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Core Imports
ACREPipeline = None
try:
    from forensics_fastapi.forensics.pipeline import ACREPipeline
except ImportError:
    # Fallback for local dev if not installed as package
    try:
        from forensics.pipeline import ACREPipeline
    except ImportError:
        pass

app = typer.Typer(help="ACRE Forensics Sandbox CLI")
console = Console()


# --- Reusable Logic Functions ---

def get_health_status() -> List[Dict[str, str]]:
    """Return health check results as a list of dictionaries."""
    results = []

    # Check 1: Python Env
    results.append({
        "component": "Python Runtime",
        "status": "OK",
        "details": platform.python_version()
    })

    # Check 2: Imports
    try:
        pass  # ACREPipeline is loaded earlier
        results.append({
            "component": "Forensics Module",
            "status": "OK",
            "details": "Imported successfully"
        })
    except ImportError as e:
        results.append({
            "component": "Forensics Module",
            "status": "FAIL",
            "details": str(e)
        })

    # Check 3: R2 Mounts
    evidence_path = "/workspace/src/forensics/evidence"
    if os.path.exists(evidence_path):
        # Check write access
        try:
            test_file = f"{evidence_path}/.health_check"
            with open(test_file, 'w') as f:
                f.write("ok")
            os.remove(test_file)
            results.append({
                "component": "R2 Evidence Mount",
                "status": "OK",
                "details": f"Writable: {evidence_path}"
            })
        except Exception as e:
            results.append({
                "component": "R2 Evidence Mount",
                "status": "WARNING",
                "details": f"Read-only or Error: {e}"
            })
    else:
        results.append({
            "component": "R2 Evidence Mount",
            "status": "MISSING",
            "details": "Not found (Dev mode?)"
        })
    
    return results


def get_system_info() -> Dict[str, Any]:
    """Return system information."""
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
        "env": dict(os.environ),
    }


def execute_command(cmd: str) -> Dict[str, Any]:
    """Execute a shell command and return result dict."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "returncode": 1
        }


async def run_scan_logic(target: str, auto_fix: bool = False):
    """Run the pipeline logic. (Wrapper for ACREPipeline)"""
    if not ACREPipeline:
        raise ImportError("ACREPipeline module could not be imported")
    pipeline = ACREPipeline()
    real_target = target if target != "all" else "src/forensics/evidence"
    await pipeline.run_pipeline(real_target)
    return True


# --- CLI Commands (Wrappers) ---

@app.command()
def scan(
    target: str = typer.Option("all", help="Target evidence directory or file"),
    auto_fix: bool = typer.Option(False, help="Attempt automatic repair of issues"),
):
    """
    Run the forensic investigation pipeline.
    """
    console.print(Panel(f"[bold blue]ACRE Forensics Pipeline[/bold blue]\nTarget: [cyan]{target}[/cyan]"))

    with console.status("[bold green]Initializing Pipeline...[/bold green]") as status:
        try:
            status.update(f"[bold green]Scanning {target}...[/bold green]")
            asyncio.run(run_scan_logic(target, auto_fix))
            console.print("[bold green]✅ Scan Completed Successfully[/bold green]")
        except Exception as e:
            console.print(f"[bold red]❌ Scan Failed:[/bold red] {e}")
            sys.exit(1)


@app.command()
def health():
    """
    Perform a self-diagnostic health check.
    """
    results = get_health_status()
    table = Table(title="System Health")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    for r in results:
        style = "[red]" if r["status"] == "FAIL" else "[yellow]" if r["status"] == "WARNING" else "green"
        status_text = r["status"] if style == "green" else f"{style}{r['status']}[/]"
        table.add_row(r["component"], status_text, r["details"])

    console.print(table)


@app.command()
def sysinfo():
    """
    Dump system information (JSON-like) for Agent SDK consumption.
    """
    info = get_system_info()
    console.print_json(data=info)


@app.command()
def exec(
    cmd: str = typer.Argument(..., help="Command to execute via subprocess"),
):
    """
    Execute a raw shell command and print output (wrapper).
    """
    result = execute_command(cmd)
    if result.get("stdout"):
        console.print(result["stdout"], end="")
    if result.get("stderr"):
        console.print(f"[red]{result['stderr']}[/red]", end="")
    
    if not result["success"]:
        if "error" in result:
             console.print(f"[bold red]Exec Failed:[/bold red] {result['error']}")
        sys.exit(result["returncode"])


if __name__ == "__main__":
    app()
