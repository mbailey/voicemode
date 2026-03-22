#!/usr/bin/env npx tsx
/**
 * VoiceMode Channel Server
 *
 * A minimal MCP channel server that pushes inbound voice events into a
 * Claude Code session. Declares the experimental claude/channel capability
 * and sends notifications/claude/channel notifications.
 *
 * Usage:
 *   npx tsx channel/index.ts
 *
 * Load as a development channel:
 *   claude --dangerously-load-development-channels server:voicemode-channel
 *
 * For testing, the server listens on a local HTTP port (default 8787) so you
 * can simulate inbound voice events with curl:
 *
 *   curl -X POST http://localhost:8787/event \
 *     -H 'Content-Type: application/json' \
 *     -d '{"caller": "mike", "transcript": "Hey Claude, what time is it?", "device_id": "abc123"}'
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from '@modelcontextprotocol/sdk/types.js'
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { appendFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'
import { randomBytes } from 'node:crypto'
import { GatewayClient } from './gateway.js'

// ---------------------------------------------------------------------------
// Explicit opt-in gate -- channel server must NOT connect to external services
// unless the user has deliberately enabled it. This prevents surprise outbound
// WebSocket connections when someone loads dev channels for other reasons.
// ---------------------------------------------------------------------------
if (process.env.VOICEMODE_CHANNEL_ENABLED !== 'true') {
  process.stderr.write(
    'VoiceMode channel server disabled. Set VOICEMODE_CHANNEL_ENABLED=true to enable.\n'
  )
  process.exit(0)
}

const CHANNEL_NAME = 'voicemode-channel'
const CHANNEL_VERSION = '0.1.0'
const HTTP_PORT = parseInt(process.env.VOICEMODE_CHANNEL_PORT ?? '8787', 10)

const INSTRUCTIONS = [
  'Events from VoiceMode appear as <channel source="voicemode-channel" caller="NAME">TRANSCRIPT</channel>.',
  'These are inbound voice messages from a user speaking on their phone or web app.',
  'Respond using the voicemode-channel reply tool (NOT the converse tool from a different server).',
  'The reply tool sends your response back through the same channel connection,',
  'keeping the conversation in the same thread on the user\'s device.',
  'Address the caller by name.',
  'Keep responses concise -- the user is listening via text-to-speech.',
].join(' ')

// ---------------------------------------------------------------------------
// MCP server with channel capability
// ---------------------------------------------------------------------------

const mcp = new Server(
  { name: CHANNEL_NAME, version: CHANNEL_VERSION },
  {
    capabilities: {
      tools: {},
      experimental: { 'claude/channel': {} },
    },
    instructions: INSTRUCTIONS,
  },
)

// ---------------------------------------------------------------------------
// Generate unique message IDs
// ---------------------------------------------------------------------------

function generate_message_id(): string {
  return `msg-${Date.now()}-${randomBytes(6).toString('hex')}`
}

// ---------------------------------------------------------------------------
// MCP tool handlers (reply tool)
// ---------------------------------------------------------------------------

mcp.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'reply',
        description:
          'Send a voice reply to the user through VoiceMode. ' +
          'Use this to respond to inbound voice channel events. ' +
          'The reply is spoken aloud on the user\'s device via TTS.',
        inputSchema: {
          type: 'object' as const,
          properties: {
            text: {
              type: 'string',
              description: 'The message to speak to the user',
            },
            voice: {
              type: 'string',
              description: 'TTS voice name (optional, uses device default if omitted)',
            },
            wait_for_response: {
              type: 'boolean',
              description: 'Whether to listen for user response after speaking (default: false)',
            },
          },
          required: ['text'],
        },
      },
    ],
  }
})

mcp.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params

  if (name !== 'reply') {
    return {
      content: [{ type: 'text', text: `Unknown tool: ${name}` }],
      isError: true,
    }
  }

  // Validate arguments
  const text = (args as Record<string, unknown>)?.text
  if (typeof text !== 'string' || text.trim().length === 0) {
    return {
      content: [{ type: 'text', text: 'Error: text parameter is required and must be non-empty' }],
      isError: true,
    }
  }

  const voice = (args as Record<string, unknown>)?.voice as string | undefined
  const wait_for_response = (args as Record<string, unknown>)?.wait_for_response as boolean | undefined

  // Check gateway connection
  if (!gateway || gateway.state !== 'connected') {
    return {
      content: [{ type: 'text', text: 'Error: Not connected to VoiceMode gateway. Waiting for reconnect.' }],
      isError: true,
    }
  }

  // Build speak message and send through gateway WebSocket
  const msg_id = generate_message_id()
  const speak_msg: Record<string, unknown> = {
    type: 'speak',
    id: msg_id,
    text: text.trim(),
    timestamp: Date.now(),
  }
  if (voice) speak_msg.voice = voice
  if (wait_for_response) speak_msg.waitForResponse = true

  const sent = gateway.send_message(speak_msg)
  if (!sent) {
    return {
      content: [{ type: 'text', text: 'Error: Failed to send speak message -- WebSocket not open' }],
      isError: true,
    }
  }

  log(`Sent reply via gateway: id=${msg_id} text="${truncate(text.trim(), 80)}"`)

  return {
    content: [{
      type: 'text',
      text: `Reply sent (id: ${msg_id}). Text: "${truncate(text.trim(), 120)}"`,
    }],
  }
})

// ---------------------------------------------------------------------------
// Push a channel notification for an inbound voice event
// ---------------------------------------------------------------------------

async function push_voice_event(
  caller: string,
  transcript: string,
  device_id?: string,
): Promise<void> {
  const meta: Record<string, string> = { caller }
  if (device_id) {
    meta.device_id = device_id
  }

  await mcp.notification({
    method: 'notifications/claude/channel',
    params: {
      content: transcript,
      meta,
    },
  })

  log(`Pushed channel notification: caller=${caller} transcript="${truncate(transcript, 80)}"`)
}

// ---------------------------------------------------------------------------
// Local HTTP server for testing (simulates inbound voice events)
// ---------------------------------------------------------------------------

interface VoiceEventPayload {
  caller: string
  transcript: string
  device_id?: string
}

function is_voice_event(body: unknown): body is VoiceEventPayload {
  if (typeof body !== 'object' || body === null) return false
  const obj = body as Record<string, unknown>
  return typeof obj.caller === 'string' && typeof obj.transcript === 'string'
}

function start_http_server(): void {
  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    // Health check
    if (req.method === 'GET' && req.url === '/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ status: 'ok', channel: CHANNEL_NAME, version: CHANNEL_VERSION }))
      return
    }

    // Voice event endpoint
    if (req.method === 'POST' && req.url === '/event') {
      let body = ''
      req.on('data', (chunk: Buffer) => { body += chunk.toString() })
      req.on('end', () => {
        try {
          const payload: unknown = JSON.parse(body)
          if (!is_voice_event(payload)) {
            res.writeHead(400, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify({ error: 'Invalid payload. Required: { caller: string, transcript: string, device_id?: string }' }))
            return
          }

          push_voice_event(payload.caller, payload.transcript, payload.device_id)
            .then(() => {
              res.writeHead(200, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ status: 'sent' }))
            })
            .catch((err: unknown) => {
              const message = err instanceof Error ? err.message : String(err)
              log(`Error pushing notification: ${message}`)
              res.writeHead(500, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ error: message }))
            })
        } catch {
          res.writeHead(400, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: 'Invalid JSON' }))
        }
      })
      return
    }

    res.writeHead(404, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ error: 'Not found. Try POST /event or GET /health' }))
  })

  server.listen(HTTP_PORT, '127.0.0.1', () => {
    log(`HTTP test server listening on http://127.0.0.1:${HTTP_PORT}`)
    log(`  POST /event  -- push a voice event`)
    log(`  GET  /health -- health check`)
  })

  server.on('error', (err: Error) => {
    if ((err as NodeJS.ErrnoException).code === 'EADDRINUSE') {
      log(`Port ${HTTP_PORT} in use, skipping HTTP test server (set VOICEMODE_CHANNEL_PORT to change)`)
    } else {
      log(`HTTP server error: ${err.message}`)
    }
  })
}

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

const LOG_DIR = join(homedir(), '.voicemode', 'logs')
const LOG_FILE = join(LOG_DIR, 'channel.log')
const DEBUG = process.env.VOICEMODE_CHANNEL_DEBUG === '1' || process.env.VOICEMODE_CHANNEL_DEBUG === 'true'

// Ensure log directory exists
try { mkdirSync(LOG_DIR, { recursive: true }) } catch { /* ignore */ }

function log(message: string, level: 'INFO' | 'DEBUG' | 'WARN' | 'ERROR' = 'INFO'): void {
  if (level === 'DEBUG' && !DEBUG) return
  const ts = new Date().toISOString()
  const line = `${ts} [${level}] [${CHANNEL_NAME}] ${message}\n`
  // Always write to stderr (Claude Code captures this)
  process.stderr.write(line)
  // Also write to log file for debugging
  try { appendFileSync(LOG_FILE, line) } catch { /* ignore */ }
}

function truncate(str: string, max_length: number): string {
  if (str.length <= max_length) return str
  return str.slice(0, max_length - 3) + '...'
}

// ---------------------------------------------------------------------------
// WebSocket gateway connection
// ---------------------------------------------------------------------------

let gateway: GatewayClient | null = null

function start_gateway(): void {
  gateway = new GatewayClient(log)

  gateway.on('connected', () => {
    log('Gateway connection established -- ready to receive voice events')
  })

  gateway.on('disconnected', () => {
    log('Gateway connection lost')
  })

  gateway.on('state', (state: string) => {
    log(`Gateway state: ${state}`)
  })

  // Handle inbound messages from the gateway (voice event pipeline)
  gateway.on('message', (msg: Record<string, unknown>) => {
    if (msg.type !== 'user_message_delivery') {
      log(`Ignoring message type: ${String(msg.type)}`)
      return
    }

    const text = msg.text
    const from = msg.from
    const user_id = msg.userId

    // Validate required fields
    if (typeof text !== 'string' || text.trim().length === 0) {
      log('Dropping user_message_delivery: missing or empty text field')
      return
    }

    // Caller identity: use "from" field if available, fall back to userId
    const caller = typeof from === 'string' && from.length > 0
      ? from
      : typeof user_id === 'string' && user_id.length > 0
        ? user_id
        : 'unknown'

    // device_id is not present on user_message_delivery -- use userId as a routing hint
    const device_id = typeof user_id === 'string' && user_id.length > 0
      ? user_id
      : undefined

    log(`Received voice event: from="${caller}" text="${truncate(text.trim(), 80)}"`)

    push_voice_event(caller, text.trim(), device_id).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : String(err)
      log(`Error pushing voice event to channel: ${message}`)
    })
  })

  // Start the connection (non-blocking -- reconnects in the background)
  gateway.start().catch((err: unknown) => {
    const message = err instanceof Error ? err.message : String(err)
    log(`Gateway start error: ${message}`)
  })
}

// ---------------------------------------------------------------------------
// Clean shutdown
// ---------------------------------------------------------------------------

async function shutdown(signal: string): Promise<void> {
  log(`Received ${signal}, shutting down...`)

  if (gateway) {
    await gateway.shutdown()
  }

  // Give a moment for cleanup, then exit
  setTimeout(() => process.exit(0), 500)
}

process.on('SIGTERM', () => { shutdown('SIGTERM') })
process.on('SIGINT', () => { shutdown('SIGINT') })

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  log(`Starting ${CHANNEL_NAME} v${CHANNEL_VERSION}`)

  // Start MCP stdio transport (communicates with Claude Code)
  const transport = new StdioServerTransport()
  await mcp.connect(transport)
  log('MCP channel server connected via stdio')

  // Connect to the voicemode.dev WebSocket gateway
  start_gateway()

  // Start local HTTP server for testing inbound events
  start_http_server()
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? err.message : String(err)
  process.stderr.write(`Fatal: ${message}\n`)
  process.exit(1)
})
