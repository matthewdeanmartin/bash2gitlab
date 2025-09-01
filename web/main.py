#!/usr/bin/env python3
"""
FastAPI server for bash2gitlab web interface
Provides REST API endpoints for the accessible web UI
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bash2gitlab.commands.clean_all import clean_targets
# Import your existing bash2gitlab modules
from bash2gitlab.commands.compile_all import run_compile_all
from bash2gitlab.commands.decompile_all import run_decompile_gitlab_tree
from bash2gitlab.commands.lint_all import lint_output_folder, summarize_results
from bash2gitlab.config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Task storage (in production, use Redis or database)
tasks: dict[str, dict[str, Any]] = {}
configs: dict[str, dict[str, Any]] = {}

app = FastAPI(title="bash2gitlab API", description="Accessible API for bash2gitlab operations", version="1.0.0", docs_url="/docs", redoc_url="/redoc")

# Enable CORS for web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your web interface URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request/response validation
class OperationConfig(BaseModel):
    inputDir: str = Field(..., description="Input directory path")
    outputDir: str = Field(..., description="Output directory path")
    dryRun: bool = Field(default=False, description="Perform dry run without file changes")
    verbose: bool = Field(default=False, description="Enable verbose logging")
    force: bool = Field(default=False, description="Force overwrite existing files")
    parallelism: int | None = Field(default=None, description="Number of parallel processes")


class ValidationRequest(BaseModel):
    inputDir: str
    outputDir: str


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str] | None = None
    warnings: list[str] | None = None
    details: str | None = None


class TaskResponse(BaseModel):
    task_id: str
    status: str = "started"
    message: str = "Operation initiated"


class TaskStatus(BaseModel):
    task_id: str
    status: str  # started, running, completed, failed, cancelled
    progress: int = Field(default=0, ge=0, le=100)
    current_step: str | None = None
    messages: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class TaskResults(BaseModel):
    task_id: str
    summary: str
    files_processed: int | None = None
    output_files: list[str] | None = None
    warnings: list[str] | None = None


class ConfigData(BaseModel):
    inputDir: str | None = None
    outputDir: str | None = None
    operation: str | None = None
    dryRun: bool = False
    force: bool = False
    verbose: bool = False
    audioFeedback: bool = True
    language: str = "en"


# Helper functions
def create_task(operation: str) -> str:
    """Create a new task and return its ID"""
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"id": task_id, "operation": operation, "status": "started", "progress": 0, "current_step": f"Initializing {operation}", "messages": [], "error": None, "started_at": datetime.now(), "completed_at": None, "results": {}}
    return task_id


def update_task(task_id: str, **kwargs):
    """Update task status"""
    if task_id in tasks:
        tasks[task_id].update(kwargs)
        if kwargs.get("status") in ["completed", "failed", "cancelled"]:
            tasks[task_id]["completed_at"] = datetime.now()


def log_task_message(task_id: str, message: str):
    """Add a log message to task"""
    if task_id in tasks:
        tasks[task_id]["messages"].append(message)
        logger.info(f"Task {task_id}: {message}")


# API Endpoints


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "bash2gitlab-api", "version": "1.0.0"}


@app.post("/api/v1/validate", response_model=ValidationResponse)
async def validate_config(request: ValidationRequest):
    """Validate configuration before running operations"""
    errors = []
    warnings = []

    # Check input directory
    input_path = Path(request.inputDir)
    if not input_path.exists():
        errors.append(f"Input directory does not exist: {request.inputDir}")
    elif not input_path.is_dir():
        errors.append(f"Input path is not a directory: {request.inputDir}")
    else:
        # Check for .gitlab-ci.yml files
        gitlab_files = list(input_path.rglob("*.gitlab-ci.yml")) + list(input_path.rglob(".gitlab-ci.yml"))
        if not gitlab_files:
            warnings.append("No .gitlab-ci.yml files found in input directory")

    # Check output directory
    output_path = Path(request.outputDir)
    if output_path.exists() and not output_path.is_dir():
        errors.append(f"Output path exists but is not a directory: {request.outputDir}")

    # Check permissions
    try:
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
        test_file = output_path / "test_write_permission.tmp"
        test_file.touch()
        test_file.unlink()
    except PermissionError:
        errors.append(f"No write permission for output directory: {request.outputDir}")
    except Exception as e:
        errors.append(f"Output directory validation failed: {str(e)}")

    is_valid = len(errors) == 0
    details = f"Input: {request.inputDir}, Output: {request.outputDir}"

    return ValidationResponse(valid=is_valid, errors=errors if errors else None, warnings=warnings if warnings else None, details=details)


@app.post("/api/v1/compile", response_model=TaskResponse)
async def start_compile(config: OperationConfig, background_tasks: BackgroundTasks):
    """Start a compile operation"""
    task_id = create_task("compile")

    background_tasks.add_task(run_compile_operation, task_id, config.inputDir, config.outputDir, config.dryRun, config.force, config.parallelism or 4)

    return TaskResponse(task_id=task_id, message="Compile operation started")


@app.post("/api/v1/clean", response_model=TaskResponse)
async def start_clean(config: OperationConfig, background_tasks: BackgroundTasks):
    """Start a clean operation"""
    task_id = create_task("clean")

    background_tasks.add_task(run_clean_operation, task_id, config.outputDir, config.dryRun)

    return TaskResponse(task_id=task_id, message="Clean operation started")


@app.post("/api/v1/lint", response_model=TaskResponse)
async def start_lint(config: OperationConfig, background_tasks: BackgroundTasks):
    """Start a lint operation"""
    task_id = create_task("lint")

    background_tasks.add_task(run_lint_operation, task_id, config.outputDir, config.verbose)

    return TaskResponse(task_id=task_id, message="Lint operation started")


@app.post("/api/v1/decompile", response_model=TaskResponse)
async def start_decompile(config: OperationConfig, background_tasks: BackgroundTasks):
    """Start a decompile operation"""
    task_id = create_task("decompile")

    background_tasks.add_task(run_decompile_operation, task_id, config.inputDir, config.outputDir, config.dryRun)

    return TaskResponse(task_id=task_id, message="Decompile operation started")


@app.get("/api/v1/status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get status of a running task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    return TaskStatus(**task)


@app.get("/api/v1/results/{task_id}", response_model=TaskResults)
async def get_task_results(task_id: str):
    """Get results of a completed task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not completed")

    results = task.get("results", {})
    return TaskResults(task_id=task_id, summary=results.get("summary", "Operation completed"), files_processed=results.get("files_processed"), output_files=results.get("output_files"), warnings=results.get("warnings"))


@app.post("/api/v1/cancel/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a running task"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    if task["status"] in ["completed", "failed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Task already finished")

    update_task(task_id, status="cancelled", error="Cancelled by user")
    log_task_message(task_id, "Operation cancelled by user")

    return {"message": "Task cancelled", "task_id": task_id}


@app.get("/api/v1/tasks")
async def list_tasks():
    """List all tasks"""
    return {"tasks": [{"task_id": task_id, "operation": task["operation"], "status": task["status"], "started_at": task["started_at"].isoformat(), "progress": task["progress"]} for task_id, task in tasks.items()]}


# Configuration endpoints
@app.post("/api/v1/config")
async def save_config(config_data: ConfigData):
    """Save configuration"""
    config_id = "default"  # Could be user-specific in the future
    configs[config_id] = config_data.dict()

    # Optionally save to file
    try:
        config_file = Path("bash2gitlab-web-config.json")
        with config_file.open("w") as f:
            json.dump(configs[config_id], f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save config to file: {e}")

    return {"message": "Configuration saved", "config_id": config_id}


@app.get("/api/v1/config", response_model=ConfigData)
async def load_config():
    """Load configuration"""
    config_id = "default"

    # Try to load from file first
    try:
        config_file = Path("bash2gitlab-web-config.json")
        if config_file.exists():
            with config_file.open("r") as f:
                file_config = json.load(f)
                configs[config_id] = file_config
    except Exception as e:
        logger.warning(f"Failed to load config from file: {e}")

    if config_id not in configs:
        # Return default config
        return ConfigData()

    return ConfigData(**configs[config_id])


# Background task functions
async def run_compile_operation(task_id: str, input_dir: str, output_dir: str, dry_run: bool, force: bool, parallelism: int):
    """Background task for compile operation"""
    try:
        update_task(task_id, status="running", progress=10, current_step="Starting compilation")
        log_task_message(task_id, f"Compiling from {input_dir} to {output_dir}")

        if dry_run:
            log_task_message(task_id, "DRY RUN MODE - No files will be modified")

        update_task(task_id, progress=25, current_step="Processing templates")

        # Call your existing compile function
        in_path = Path(input_dir)
        out_path = Path(output_dir)

        # Create a progress callback
        def progress_callback(current: int, total: int, filename: str):
            progress = 25 + int((current / total) * 60)  # 25-85%
            update_task(task_id, progress=progress, current_step=f"Processing {filename} ({current}/{total})")
            log_task_message(task_id, f"Processing: {filename}")

        # Run the actual compilation
        files_processed = await asyncio.get_event_loop().run_in_executor(None, lambda: run_compile_all_with_progress(in_path, out_path, dry_run, parallelism, force, task_id, progress_callback))

        update_task(task_id, progress=95, current_step="Finalizing output")
        log_task_message(task_id, f"Compilation completed. {files_processed} files processed.")

        # Store results
        results = {"summary": f"Successfully compiled {files_processed} files", "files_processed": files_processed, "output_files": list(out_path.rglob("*.yml")) + list(out_path.rglob("*.yaml"))}

        update_task(task_id, status="completed", progress=100, current_step="Complete", results=results)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Compile operation failed for task {task_id}: {error_msg}")
        update_task(task_id, status="failed", error=error_msg)
        log_task_message(task_id, f"ERROR: {error_msg}")


def run_compile_all_with_progress(input_path: Path, output_path: Path, dry_run: bool, parallelism: int, force: bool, task_id: str, progress_callback):
    """Wrapper for compile_all with progress reporting"""
    try:
        # Get list of files to process
        yaml_files = list(input_path.rglob("*.yml")) + list(input_path.rglob("*.yaml"))
        total_files = len(yaml_files)

        if tasks[task_id]["status"] == "cancelled":
            return 0

        # Call the actual function
        run_compile_all(uncompiled_path=input_path, output_path=output_path, dry_run=dry_run, parallelism=parallelism, force=force)

        return total_files

    except Exception as e:
        logger.error(f"Compile execution failed: {e}")
        raise


async def run_clean_operation(task_id: str, output_dir: str, dry_run: bool):
    """Background task for clean operation"""
    try:
        update_task(task_id, status="running", progress=20, current_step="Scanning output directory")
        log_task_message(task_id, f"Cleaning directory: {output_dir}")

        if dry_run:
            log_task_message(task_id, "DRY RUN MODE - No files will be deleted")

        update_task(task_id, progress=50, current_step="Identifying files to clean")

        # Run the actual clean operation
        out_path = Path(output_dir)
        await asyncio.get_event_loop().run_in_executor(None, lambda: clean_targets(out_path, dry_run=dry_run))

        update_task(task_id, progress=90, current_step="Finalizing cleanup")
        log_task_message(task_id, "Clean operation completed")

        results = {
            "summary": f"Clean operation completed on {output_dir}",
        }

        update_task(task_id, status="completed", progress=100, current_step="Complete", results=results)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Clean operation failed for task {task_id}: {error_msg}")
        update_task(task_id, status="failed", error=error_msg)
        log_task_message(task_id, f"ERROR: {error_msg}")


async def run_lint_operation(task_id: str, output_dir: str, verbose: bool):
    """Background task for lint operation"""
    try:
        update_task(task_id, status="running", progress=15, current_step="Connecting to GitLab API")
        log_task_message(task_id, f"Linting files in: {output_dir}")

        update_task(task_id, progress=30, current_step="Scanning YAML files")

        # Get GitLab connection info from config
        gitlab_url = config.lint_gitlab_url or "https://gitlab.com"
        project_id = config.lint_project_id

        update_task(task_id, progress=50, current_step="Running GitLab CI Lint")

        # Run the actual lint operation
        out_path = Path(output_dir)
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: lint_output_folder(
                output_root=out_path,
                gitlab_url=gitlab_url,
                private_token=None,  # Will need to be provided via API
                project_id=project_id,
                parallelism=2,
                timeout=20,
            ),
        )

        update_task(task_id, progress=80, current_step="Analyzing results")

        # Summarize results
        ok_count, fail_count = summarize_results(results)

        log_task_message(task_id, f"Lint completed: {ok_count} valid, {fail_count} invalid files")

        summary = f"Linting completed: {ok_count} valid files, {fail_count} files with issues"

        task_results = {"summary": summary, "files_processed": ok_count + fail_count, "warnings": [f"{fail_count} files had validation issues"] if fail_count > 0 else None}

        update_task(task_id, status="completed", progress=100, current_step="Complete", results=task_results)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Lint operation failed for task {task_id}: {error_msg}")
        update_task(task_id, status="failed", error=error_msg)
        log_task_message(task_id, f"ERROR: {error_msg}")


async def run_decompile_operation(task_id: str, input_dir: str, output_dir: str, dry_run: bool):
    """Background task for decompile operation"""
    try:
        update_task(task_id, status="running", progress=20, current_step="Starting decompile")
        log_task_message(task_id, f"Decompiling from {input_dir} to {output_dir}")

        if dry_run:
            log_task_message(task_id, "DRY RUN MODE - No files will be modified")

        update_task(task_id, progress=40, current_step="Processing YAML files")

        # Run the actual decompile operation
        in_path = Path(input_dir)
        out_path = Path(output_dir)

        yml_count, jobs, scripts = await asyncio.get_event_loop().run_in_executor(None, lambda: run_decompile_gitlab_tree(input_root=in_path, output_dir=out_path, dry_run=dry_run))

        update_task(task_id, progress=90, current_step="Finalizing decompilation")

        log_task_message(task_id, f"Decompiled {yml_count} YAML files, {jobs} jobs, created {scripts} scripts")

        results = {"summary": f"Decompiled {yml_count} YAML files, processed {jobs} jobs, created {scripts} script files", "files_processed": yml_count}

        update_task(task_id, status="completed", progress=100, current_step="Complete", results=results)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Decompile operation failed for task {task_id}: {error_msg}")
        update_task(task_id, status="failed", error=error_msg)
        log_task_message(task_id, f"ERROR: {error_msg}")


# Cleanup old tasks (in production, use a proper job queue)
@app.on_event("startup")
async def startup_event():
    """Cleanup tasks on startup"""
    logger.info("bash2gitlab API server starting up")

    # Clean up old task data (keep last 100 tasks)
    def cleanup_old_tasks():
        if len(tasks) > 100:
            # Keep only the 100 most recent tasks
            sorted_tasks = sorted(tasks.items(), key=lambda x: x[1]["started_at"], reverse=True)
            tasks.clear()
            tasks.update(dict(sorted_tasks[:100]))

    cleanup_old_tasks()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="bash2gitlab API Server")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()

    print(f"""
🚀 Starting bash2gitlab API Server

   API URL: http://{args.host}:{args.port}
   Docs: http://{args.host}:{args.port}/docs
   Health Check: http://{args.host}:{args.port}/api/v1/health

   Web Interface should connect to: http://{args.host}:{args.port}
    """)

    uvicorn.run("bash2gitlab_api:app" if not args.reload else __file__ + ":app", host=args.host, port=args.port, reload=args.reload, log_level="info")
