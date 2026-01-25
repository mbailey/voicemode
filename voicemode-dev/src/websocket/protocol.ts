/**
 * WebSocket Protocol Types for VoiceMode
 *
 * Defines all message types for communication between:
 * - iOS App (Client) → voicemode.dev (Server)
 * - voicemode.dev (Server) → iOS App (Client)
 *
 * See ARCHITECTURE.md section 3 for protocol specification.
 */

// ============================================================================
// Base Message Types
// ============================================================================

/** Base interface for all messages */
export interface BaseMessage {
  /** Message type identifier */
  type: string;
  /** Optional message ID for correlation */
  id?: string;
  /** Timestamp when message was created */
  timestamp?: number;
}

// ============================================================================
// Client → Server Messages
// ============================================================================

/**
 * Auth message: Authenticate the WebSocket connection.
 * Typically sent if the initial connection was made without a token,
 * or to re-authenticate with a new token.
 */
export interface AuthMessage extends BaseMessage {
  type: "auth";
  /** JWT token from Auth0 */
  token: string;
}

/**
 * Ready message: Client signals it's ready to receive commands.
 * Sent after connection is established and client is initialized.
 */
export interface ReadyMessage extends BaseMessage {
  type: "ready";
  /** Optional device information */
  device?: {
    /** Platform (ios, android, web) */
    platform?: string;
    /** App version */
    appVersion?: string;
    /** Device model */
    model?: string;
    /** Operating system version */
    osVersion?: string;
  };
  /** Supported features/capabilities */
  capabilities?: {
    /** TTS engine available */
    tts?: boolean;
    /** STT engine available */
    stt?: boolean;
    /** Maximum audio duration in seconds */
    maxAudioDuration?: number;
  };
}

/**
 * Transcription message: Client sends STT result after recording.
 * Sent in response to a 'listen' command from the server.
 */
export interface TranscriptionMessage extends BaseMessage {
  type: "transcription";
  /** The transcribed text from speech */
  text: string;
  /** ID of the 'listen' or 'speak' message this responds to */
  id: string;
  /** Confidence score (0-1) if available */
  confidence?: number;
  /** Duration of the audio in seconds */
  duration?: number;
  /** Whether transcription was final or interim */
  isFinal?: boolean;
  /** Language detected or used */
  language?: string;
}

/**
 * Heartbeat message: Keep-alive ping from client.
 * Should be sent periodically to prevent connection timeout.
 */
export interface HeartbeatMessage extends BaseMessage {
  type: "heartbeat";
}

/** Union type of all client-to-server messages */
export type ClientMessage =
  | AuthMessage
  | ReadyMessage
  | TranscriptionMessage
  | HeartbeatMessage;

// ============================================================================
// Server → Client Messages
// ============================================================================

/**
 * Speak message: Server sends text for TTS playback.
 * Client should synthesize and play this text.
 */
export interface SpeakMessage extends BaseMessage {
  type: "speak";
  /** Message ID for correlation with transcription response */
  id: string;
  /** Text to speak via TTS */
  text: string;
  /** Optional voice to use */
  voice?: string;
  /** Optional speech rate (0.5-2.0, default 1.0) */
  speed?: number;
  /** Whether to wait for user response after speaking */
  waitForResponse?: boolean;
  /** Optional TTS instructions/style */
  instructions?: string;
}

/**
 * Listen message: Server requests client to start recording.
 * Client should start STT and send transcription when done.
 */
export interface ListenMessage extends BaseMessage {
  type: "listen";
  /** Message ID for correlation with transcription response */
  id: string;
  /** Maximum recording duration in seconds */
  maxDuration?: number;
  /** Minimum recording duration before silence detection */
  minDuration?: number;
  /** Whether to use voice activity detection (VAD) */
  useVAD?: boolean;
  /** Language hint for STT */
  language?: string;
  /** Optional prompt/context for better transcription */
  prompt?: string;
}

/**
 * Stop message: Server requests client to stop current operation.
 * Used to cancel ongoing TTS playback or STT recording.
 */
export interface StopMessage extends BaseMessage {
  type: "stop";
  /** What to stop: 'tts', 'stt', or 'all' */
  target?: "tts" | "stt" | "all";
  /** Reason for stopping */
  reason?: string;
}

/**
 * Ack message: Server acknowledges receipt of a client message.
 * Provides confirmation that a message was received and processed.
 */
export interface AckMessage extends BaseMessage {
  type: "ack";
  /** ID of the message being acknowledged */
  id: string;
  /** Status of the acknowledged operation */
  status: "ok" | "error";
  /** Optional error message if status is 'error' */
  error?: string;
  /** Optional error code */
  errorCode?: string;
}

/**
 * Connected message: Server confirms connection established.
 * Sent immediately after WebSocket connection is accepted.
 */
export interface ConnectedMessage extends BaseMessage {
  type: "connected";
  /** Whether the connection is authenticated */
  authenticated: boolean;
  /** User ID if authenticated */
  userId?: string | null;
  /** Session ID for reconnection */
  sessionId?: string;
  /** Server timestamp */
  timestamp: number;
}

/**
 * Heartbeat acknowledgment: Server responds to heartbeat.
 */
export interface HeartbeatAckMessage extends BaseMessage {
  type: "heartbeat_ack";
  /** Server timestamp */
  timestamp: number;
}

/**
 * Error message: Server reports an error condition.
 */
export interface ErrorMessage extends BaseMessage {
  type: "error";
  /** Error code for programmatic handling */
  code: string;
  /** Human-readable error message */
  message: string;
  /** Server timestamp */
  timestamp: number;
  /** Optional details for debugging */
  details?: unknown;
}

/** Union type of all server-to-client messages */
export type ServerMessage =
  | SpeakMessage
  | ListenMessage
  | StopMessage
  | AckMessage
  | ConnectedMessage
  | HeartbeatAckMessage
  | ErrorMessage;

// ============================================================================
// Message Validation
// ============================================================================

/** Error codes for message validation */
export enum MessageErrorCode {
  PARSE_ERROR = "PARSE_ERROR",
  INVALID_MESSAGE = "INVALID_MESSAGE",
  MISSING_FIELD = "MISSING_FIELD",
  INVALID_TYPE = "INVALID_TYPE",
  UNKNOWN_TYPE = "UNKNOWN_TYPE",
  AUTH_REQUIRED = "AUTH_REQUIRED",
  INVALID_TOKEN = "INVALID_TOKEN",
}

/** Result of message validation */
export interface ValidationResult {
  valid: boolean;
  error?: string;
  errorCode?: MessageErrorCode;
}

/**
 * Validate an incoming client message.
 * Returns validation result with error details if invalid.
 */
export function validateClientMessage(data: unknown): ValidationResult {
  // Check basic structure
  if (typeof data !== "object" || data === null) {
    return {
      valid: false,
      error: "Message must be an object",
      errorCode: MessageErrorCode.INVALID_MESSAGE,
    };
  }

  const msg = data as Record<string, unknown>;

  // Check for type field
  if (!("type" in msg) || typeof msg.type !== "string") {
    return {
      valid: false,
      error: "Message must have a 'type' field",
      errorCode: MessageErrorCode.MISSING_FIELD,
    };
  }

  // Validate specific message types
  switch (msg.type) {
    case "auth":
      return validateAuthMessage(msg);
    case "ready":
      return validateReadyMessage(msg);
    case "transcription":
      return validateTranscriptionMessage(msg);
    case "heartbeat":
      // Heartbeat has no required fields beyond type
      return { valid: true };
    default:
      // Unknown message type - we handle gracefully but flag it
      return {
        valid: false,
        error: `Unknown message type: ${msg.type}`,
        errorCode: MessageErrorCode.UNKNOWN_TYPE,
      };
  }
}

/**
 * Validate an auth message.
 */
function validateAuthMessage(msg: Record<string, unknown>): ValidationResult {
  if (!msg.token || typeof msg.token !== "string") {
    return {
      valid: false,
      error: "Auth message must have a 'token' field (string)",
      errorCode: MessageErrorCode.MISSING_FIELD,
    };
  }
  if (msg.token.length < 10) {
    return {
      valid: false,
      error: "Token appears to be invalid (too short)",
      errorCode: MessageErrorCode.INVALID_TOKEN,
    };
  }
  return { valid: true };
}

/**
 * Validate a ready message.
 */
function validateReadyMessage(msg: Record<string, unknown>): ValidationResult {
  // Ready message has optional fields, but if device is present, validate it
  if (msg.device !== undefined) {
    if (typeof msg.device !== "object" || msg.device === null) {
      return {
        valid: false,
        error: "'device' field must be an object",
        errorCode: MessageErrorCode.INVALID_TYPE,
      };
    }
  }
  if (msg.capabilities !== undefined) {
    if (typeof msg.capabilities !== "object" || msg.capabilities === null) {
      return {
        valid: false,
        error: "'capabilities' field must be an object",
        errorCode: MessageErrorCode.INVALID_TYPE,
      };
    }
  }
  return { valid: true };
}

/**
 * Validate a transcription message.
 */
function validateTranscriptionMessage(
  msg: Record<string, unknown>
): ValidationResult {
  if (!msg.text || typeof msg.text !== "string") {
    return {
      valid: false,
      error: "Transcription message must have a 'text' field (string)",
      errorCode: MessageErrorCode.MISSING_FIELD,
    };
  }
  if (!msg.id || typeof msg.id !== "string") {
    return {
      valid: false,
      error: "Transcription message must have an 'id' field (string)",
      errorCode: MessageErrorCode.MISSING_FIELD,
    };
  }
  return { valid: true };
}

/**
 * Type guard to check if a message is a valid ClientMessage.
 */
export function isClientMessage(data: unknown): data is ClientMessage {
  const result = validateClientMessage(data);
  return result.valid;
}

/**
 * Parse and validate a client message from a string.
 * Returns the parsed message or null if invalid.
 */
export function parseClientMessage(
  raw: string | ArrayBuffer
): { message: ClientMessage; error?: never } | { message?: never; error: ValidationResult } {
  // Convert ArrayBuffer to string if needed
  const msgStr = typeof raw === "string" ? raw : new TextDecoder().decode(raw);

  // Parse JSON
  let data: unknown;
  try {
    data = JSON.parse(msgStr);
  } catch (e) {
    return {
      error: {
        valid: false,
        error: "Invalid JSON",
        errorCode: MessageErrorCode.PARSE_ERROR,
      },
    };
  }

  // Validate structure
  const validation = validateClientMessage(data);
  if (!validation.valid) {
    return { error: validation };
  }

  return { message: data as ClientMessage };
}

// ============================================================================
// Message Factories
// ============================================================================

/** Generate a unique message ID */
export function generateMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/** Create a speak message */
export function createSpeakMessage(
  text: string,
  options?: Partial<Omit<SpeakMessage, "type" | "text" | "id">>
): SpeakMessage {
  return {
    type: "speak",
    id: generateMessageId(),
    text,
    timestamp: Date.now(),
    ...options,
  };
}

/** Create a listen message */
export function createListenMessage(
  options?: Partial<Omit<ListenMessage, "type" | "id">>
): ListenMessage {
  return {
    type: "listen",
    id: generateMessageId(),
    timestamp: Date.now(),
    ...options,
  };
}

/** Create a stop message */
export function createStopMessage(
  target?: "tts" | "stt" | "all",
  reason?: string
): StopMessage {
  return {
    type: "stop",
    target,
    reason,
    timestamp: Date.now(),
  };
}

/** Create an ack message */
export function createAckMessage(
  messageId: string,
  status: "ok" | "error",
  error?: string,
  errorCode?: string
): AckMessage {
  return {
    type: "ack",
    id: messageId,
    status,
    error,
    errorCode,
    timestamp: Date.now(),
  };
}

/** Create an error message */
export function createErrorMessage(
  code: string,
  message: string,
  details?: unknown
): ErrorMessage {
  return {
    type: "error",
    code,
    message,
    details,
    timestamp: Date.now(),
  };
}
