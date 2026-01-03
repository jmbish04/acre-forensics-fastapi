import { type DurableObject } from 'cloudflare:workers';

export type Signal = 'SIGKILL' | 'SIGINT' | 'SIGTERM';
export type SignalInteger = number;

export const signalToNumbers: Record<Signal, SignalInteger> = {
    SIGINT: 2,
    SIGTERM: 15,
    SIGKILL: 9,
};

/**
 * Request body schema for email forensic analysis
 */
export interface ForensicsAnalysisRequest {
    messageId: string;
    from: string;
    to: string;
    subject: string;
    body: string;
    headers: Record<string, string>;
    rawMessage?: string;
    analysisTypes?: string[]; // e.g., ["metadata", "content", "pattern", "security"]
    timestamp?: string;
    secrets?: {
        GCP_SERVICE_ACCOUNT?: string;
        WORKER_API_KEY?: string;
    };
    workflowId?: string;
    engagementId?: string;
}

/**
 * Response schema from the FastAPI forensics analyzer
 */
export interface ForensicsAnalysisResponse {
    messageId: string;
    analysisResults: {
        metadata?: Record<string, any>;
        content?: Record<string, any>;
        patterns?: Record<string, any>;
        security?: Record<string, any>;
    };
    processingTime: number;
    status: "success" | "error" | "partial";
    error?: string;
    deceptionScore?: number;
    vectorId?: string;
}

export interface ContainerStatus {
    id: string; // DO ID or Container ID
    state: "running" | "stopped" | "starting" | "stopping" | "errored";
    uptimeSeconds: number;
    lastPing: string;
    error?: string;
}

export interface ContainerControlRequest {
    action: "start" | "stop" | "restart";
}

/**
 * ContainerStartOptions as they come from worker types
 */
export type ContainerStartOptions = NonNullable<
    Parameters<NonNullable<DurableObject['ctx']['container']>['start']>[0]
>;

/**
 * Message structure for communication with containers
 */
export interface ContainerMessage<T = unknown> {
    type: string;
    payload?: T;
}

/**
 * Options for container configuration
 */
export interface ContainerOptions {
    /** Optional ID for the container */
    id?: string;

    /** Default port number to connect to (defaults to container.defaultPort) */
    defaultPort?: number;

    /** How long to keep the container alive without activity */
    sleepAfter?: string | number;

    /** Environment variables to pass to the container */
    envVars?: Record<string, string>;

    /** Custom entrypoint to override container default */
    entrypoint?: string[];

    /** Whether to enable internet access for the container */
    enableInternet?: boolean;
}

/**
 * Function to handle container events
 */
export type ContainerEventHandler = () => void | Promise<void>;

/**
 * Options for starting a container with specific configuration
 */
export interface ContainerStartConfigOptions {
    /** Environment variables to pass to the container */
    envVars?: Record<string, string>;
    /** Custom entrypoint to override container default */
    entrypoint?: string[];
    /** Whether to enable internet access for the container */
    enableInternet?: boolean;
}

export interface StartAndWaitForPortsOptions {
    startOptions?: ContainerStartConfigOptions;
    ports?: number | number[];
    cancellationOptions?: CancellationOptions;
}

/** cancellationOptions for startAndWaitForPorts()  */
export interface CancellationOptions {
    /** abort signal, use to abort startAndWaitForPorts manually. */
    abort?: AbortSignal;
    /** max time to get container instance and start it (application inside may not be ready), in milliseconds */
    instanceGetTimeoutMS?: number;
    /** max time to wait for application to be listening at all specified ports, in milliseconds. */
    portReadyTimeoutMS?: number;
    /** time to wait between polling, in milliseconds */
    waitInterval?: number;
}

/**
 * Options for waitForPort()
 */
export interface WaitOptions {
    /** The port number to check for readiness */
    portToCheck: number;
    /** Optional AbortSignal, use this to abort waiting for ports */
    signal?: AbortSignal;
    /** Number of attempts to wait for port to be ready */
    retries?: number;
    /** Time to wait in between polling port for readiness, in milliseconds */
    waitInterval?: number;
}

/**
 * Represents a scheduled task within a Container
 * @template T Type of the payload data
 */
export type Schedule<T = string> = {
    /** Unique identifier for the schedule */
    taskId: string;
    /** Name of the method to be called */
    callback: string;
    /** Data to be passed to the callback */
    payload: T;
} & (
        | {
            /** Type of schedule for one-time execution at a specific time */
            type: 'scheduled';
            /** Timestamp when the task should execute */
            time: number;
        }
        | {
            /** Type of schedule for delayed execution */
            type: 'delayed';
            /** Timestamp when the task should execute */
            time: number;
            /** Number of seconds to delay execution */
            delayInSeconds: number;
        }
    );

/**
 * Params sent to `onStop` method when the container stops
 */
export type StopParams = {
    exitCode: number;
    reason: 'exit' | 'runtime_signal';
};

export type ScheduleSQL = {
    id: string;
    callback: string;
    payload: string;
    type: 'scheduled' | 'delayed';
    time: number;
    delayInSeconds?: number;
};

export type State = {
    lastChange: number;
} & (
        | {
            // 'running' means that the container is trying to start and is transitioning to a healthy status.
            //           onStop might be triggered if there is an exit code, and it will transition to 'stopped'.
            status: 'running' | 'stopping' | 'stopped' | 'healthy';
        }
        | {
            status: 'stopped_with_code';
            exitCode?: number;
        }
    );

/**
 * Provider interface for container management
 */
export interface Provider {
    list(): Promise<any[]>;
    spawn(name: string, options?: any): Promise<void>;
    stop(name: string): Promise<void>;
    exec(name: string, command: string[], options?: any): Promise<any>;
    getLogs(name: string, limit?: number): Promise<any>;
    // Add fetch for HTTP proxying
    fetch(name: string, request: Request): Promise<Response>;
    execPython(name: string, code: string): Promise<any>;
}


// starting => we called start() and init the monitor promise
// running => container returned healthy on the endpoint
// unhealthy => container is unhealthy (returning not OK status codes)
// stopped => container is stopped (finished running)
// failed => container failed to run and it won't try to run again, unless called 'start' again
export type ContainerState =
    | "starting"
    | "running"
    | "unhealthy"
    | "stopped"
    | "failed"
    | "unknown";



/**
 * Container info
 */
export type ContainerInfo = {
    startupOpts: ContainerStartConfigOptions;
    name: string;
    state: ContainerState;
    bindingName: string;
};

/**
 * Container binding map
 */
export type ContainerBindingMap = Record<string, DurableObjectNamespace>;

/**
 * Forensics job interface
 */
export interface ForensicsJob {
    engagementId: string;
    emailId: string;
    source: "gmail" | "api";
    payload: any;
    createdAt: string;
}




// File operation result types
export type ProcessStatus =
    | 'starting' // Process is being initialized
    | 'running' // Process is actively running
    | 'completed' // Process exited successfully (code 0)
    | 'failed' // Process exited with non-zero code
    | 'killed' // Process was terminated by signal
    | 'error'; // Process failed to start or encountered error

export interface MkdirResult {
    success: boolean;
    path: string;
    recursive: boolean;
    timestamp: string;
    exitCode?: number;
}

export interface WriteFileResult {
    success: boolean;
    path: string;
    timestamp: string;
    exitCode?: number;
}

export interface ReadFileResult {
    success: boolean;
    path: string;
    content: string;
    timestamp: string;
    exitCode?: number;

    /**
     * Encoding used for content (utf-8 for text, base64 for binary)
     */
    encoding?: 'utf-8' | 'base64';

    /**
     * Whether the file is detected as binary
     */
    isBinary?: boolean;

    /**
     * MIME type of the file (e.g., 'image/png', 'text/plain')
     */
    mimeType?: string;

    /**
     * File size in bytes
     */
    size?: number;
}

export interface DeleteFileResult {
    success: boolean;
    path: string;
    timestamp: string;
    exitCode?: number;
}

export interface RenameFileResult {
    success: boolean;
    path: string;
    newPath: string;
    timestamp: string;
    exitCode?: number;
}

export interface MoveFileResult {
    success: boolean;
    path: string;
    newPath: string;
    timestamp: string;
    exitCode?: number;
}

export interface FileExistsResult {
    success: boolean;
    path: string;
    exists: boolean;
    timestamp: string;
}

export interface FileInfo {
    name: string;
    absolutePath: string;
    relativePath: string;
    type: 'file' | 'directory' | 'symlink' | 'other';
    size: number;
    modifiedAt: string;
    mode: string;
    permissions: {
        readable: boolean;
        writable: boolean;
        executable: boolean;
    };
}

export interface ListFilesOptions {
    recursive?: boolean;
    includeHidden?: boolean;
}

export interface ListFilesResult {
    success: boolean;
    path: string;
    files: FileInfo[];
    count: number;
    timestamp: string;
    exitCode?: number;
}

export interface GitCheckoutResult {
    success: boolean;
    repoUrl: string;
    branch: string;
    targetDir: string;
    timestamp: string;
    exitCode?: number;
}

// File Streaming Types

/**
 * SSE events for file streaming
 */
export type FileStreamEvent =
    | {
        type: 'metadata';
        mimeType: string;
        size: number;
        isBinary: boolean;
        encoding: 'utf-8' | 'base64';
    }
    | {
        type: 'chunk';
        data: string; // base64 for binary, UTF-8 for text
    }
    | {
        type: 'complete';
        bytesRead: number;
    }
    | {
        type: 'error';
        error: string;
    };

/**
 * File metadata from streaming
 */
export interface FileMetadata {
    mimeType: string;
    size: number;
    isBinary: boolean;
    encoding: 'utf-8' | 'base64';
}

/**
 * File stream chunk - either string (text) or Uint8Array (binary, auto-decoded)
 */
export type FileChunk = string | Uint8Array;

// Process management result types
export interface ProcessStartResult {
    success: boolean;
    processId: string;
    pid?: number;
    command: string;
    timestamp: string;
}

export interface ProcessListResult {
    success: boolean;
    processes: Array<{
        id: string;
        pid?: number;
        command: string;
        status: ProcessStatus;
        startTime: string;
        endTime?: string;
        exitCode?: number;
    }>;
    timestamp: string;
}

export interface ProcessInfoResult {
    success: boolean;
    process: {
        id: string;
        pid?: number;
        command: string;
        status: ProcessStatus;
        startTime: string;
        endTime?: string;
        exitCode?: number;
    };
    timestamp: string;
}

export interface ProcessKillResult {
    success: boolean;
    processId: string;
    signal?: string;
    timestamp: string;
}

export interface ProcessLogsResult {
    success: boolean;
    processId: string;
    stdout: string;
    stderr: string;
    timestamp: string;
}

export interface ProcessCleanupResult {
    success: boolean;
    cleanedCount: number;
    timestamp: string;
}

// Session management result types
export interface SessionCreateResult {
    success: boolean;
    sessionId: string;
    name?: string;
    cwd?: string;
    timestamp: string;
}

export interface SessionDeleteResult {
    success: boolean;
    sessionId: string;
    timestamp: string;
}

export interface EnvSetResult {
    success: boolean;
    timestamp: string;
}

// Port management result types
export interface PortExposeResult {
    success: boolean;
    port: number;
    url: string;
    timestamp: string;
}

export interface PortStatusResult {
    success: boolean;
    port: number;
    status: 'active' | 'inactive';
    url?: string;
    timestamp: string;
}

export interface PortListResult {
    success: boolean;
    ports: Array<{
        port: number;
        url: string;
        status: 'active' | 'inactive';
    }>;
    timestamp: string;
}

export interface PortCloseResult {
    success: boolean;
    port: number;
    timestamp: string;
}

// Code interpreter result types
export interface InterpreterHealthResult {
    success: boolean;
    status: 'healthy' | 'unhealthy';
    timestamp: string;
}

export interface ContextCreateResult {
    success: boolean;
    contextId: string;
    language: string;
    cwd?: string;
    timestamp: string;
}

export interface ContextListResult {
    success: boolean;
    contexts: Array<{
        id: string;
        language: string;
        cwd?: string;
    }>;
    timestamp: string;
}

export interface ContextDeleteResult {
    success: boolean;
    contextId: string;
    timestamp: string;
}

// Miscellaneous result types
export interface HealthCheckResult {
    success: boolean;
    status: 'healthy' | 'unhealthy';
    timestamp: string;
}

export interface ShutdownResult {
    success: boolean;
    message: string;
    timestamp: string;
}