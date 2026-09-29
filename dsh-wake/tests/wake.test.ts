/**
 * Wake-bridge tests: a real Cordis composition with a real WebServer, a real
 * AgentLoop, a scripted LLM adapter, and the plugin under test.
 *
 * Run: `TSX_TSCONFIG_PATH=./tsconfig.test.json node --import tsx/esm tests/wake.test.ts`
 */

import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { pathToFileURL } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import { Context as CordisContext } from '@deepseek-ai/cordis'
import Include from '@deepseek-ai/cordis-plugin-include'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import WebServer from '@deepseek-ai/dsh-host-webserver'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionStore from '@deepseek-ai/dsh-session'
import { bindScopeParent, createScope } from '@deepseek-ai/dsh-scope'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime, { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import { MockAdapter, textResponse } from '/home/youthz/deepseek-harness/packages/core/agent-loop/tests/mock-adapter.ts'
import * as Wake from '../src/index.ts'
import * as WakeBuilt from '../lib/index.js'

/** One scripted mock adapter answers every request with the same text. */
function scriptedAdapter(): MockAdapter {
  return new MockAdapter([textResponse('收到'), textResponse('收到'), textResponse('收到'), textResponse('收到')])
}

/** A registered tool occupying the ra2 MCP namespace, as a mounted MCP server would. */
function ra2Tool() {
  return defineContentToolFixture({
    name: 'mcp__ra2__status',
    description: 'ra2 game status',
    parameters: {},
    execute: async () => [{ type: 'text', text: 'ok' }],
  })
}

interface BootOptions {
  /** Mount the ra2 MCP tool namespace. */
  readonly ra2Tools?: boolean
  /** Register a `session/flush` listener so flush acknowledges delivery. */
  readonly durable?: boolean
  /** Number of idle agents to create; defaults to one. */
  readonly count?: number
  /** Plugins mounted after the base stack and before the wake plugin. */
  readonly before?: (ctx: Context) => Promise<void>
}

interface Booted {
  readonly ctx: Context
  readonly agents: readonly Agent[]
  readonly port: number
}

/** Boot the base stack, one or two agents, the wake plugin, and a real WebServer. */
async function boot(options: BootOptions = {}): Promise<Booted> {
  const ctx = new CordisContext()
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  ctx.llm.registerAdapter(['mock'], scriptedAdapter())
  if (options.ra2Tools !== false) ctx.tools.register(ra2Tool())
  if (options.durable !== false) ctx.on('session/flush', () => undefined)

  const agents: Agent[] = []
  const count = options.count ?? 1
  for (let index = 0; index < count; index += 1) {
    const id = index === 0 ? 'ra2-agent-a' : `ra2-agent-${String.fromCharCode(96 + index + 1)}`
    agents.push(await ctx.agentLoop.create(SessionId(id), { provider: 'mock', model: 'mock' }))
  }
  ctx.provide('sessionController', {
    resolveAgent: async (sessionId: string) => {
      const found = agents.find(agent => agent.id === sessionId)
      return found === undefined
        ? { error: { message: `session "${sessionId}" not found` } }
        : { agent: found }
    },
  } as never)
  await options.before?.(ctx)
  await ctx.plugin(Wake, {
    path: '/ra2/wake',
    maxBodyBytes: 2048,
    mcpServerName: 'ra2',
    fallbackSession: '',
    secretEnv: '',
  })
  await ctx.plugin(WebServer, { host: '127.0.0.1', port: 0, compression: 'none' })
  const port = ctx.webServer.port
  assert.ok(port > 0, 'webserver must listen')
  return { ctx, agents, port }
}

/** POST one JSON body to the wake route; `contentType: null` omits the header entirely. */
async function wake(
  port: number,
  body: unknown,
  init: { readonly contentType?: string | null; readonly method?: string } = {},
): Promise<{ readonly status: number; readonly body: Record<string, unknown> }> {
  const contentType = init.contentType === undefined ? 'application/json' : init.contentType
  const headers: Record<string, string> = {}
  if (contentType !== null) headers['content-type'] = contentType
  const response = await fetch(`http://127.0.0.1:${String(port)}/ra2/wake`, {
    method: init.method ?? 'POST',
    headers,
    ...init.method === 'GET' ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) },
  })
  const text = await response.text()
  return { status: response.status, body: JSON.parse(text) as Record<string, unknown> }
}

/** Every user-role text recorded in one agent's log. */
function userTexts(agent: Agent): string[] {
  return agent.session.snapshotEvents()
    .filter(event => event.type === 'user/message')
    .flatMap(event => event.type === 'user/message' ? event.data.content : [])
    .flatMap(block => block.type === 'text' ? [block.text] : [])
}

/** Every wake-source tag recorded in one agent's log. */
function wakeSources(agent: Agent): unknown[] {
  return agent.session.snapshotEvents()
    .filter(event => event.type === 'user/message')
    .map(event => event.type === 'user/message' ? event.data.source : undefined)
    .filter(source => (source as { kind?: string } | undefined)?.kind === 'ra2-wake')
}

/** Wait until the agent reaches idle, or fail after a bounded wait. */
async function waitForIdle(agent: Agent): Promise<void> {
  const deadline = Date.now() + 10_000
  while (agent.status !== 'idle') {
    if (Date.now() > deadline) throw new Error('agent did not return to idle')
    await new Promise(resolve => setTimeout(resolve, 10))
  }
  // The status flip precedes the durable settlement of the final event.
  await new Promise(resolve => setTimeout(resolve, 50))
}

test('a wake opens a real turn on the discovered Session', async () => {
  const { ctx, agents, port } = await boot()
  const agent = agents[0] as Agent
  try {
    const response = await wake(port, { text: '基地被打了，3 个建筑在掉血', frame: 8120, tactic: 'watch_base' })
    assert.equal(response.status, 200)
    assert.deepEqual(response.body, { ok: true, session: 'ra2-agent-a' })
    await waitForIdle(agent)
    assert.deepEqual(userTexts(agent), ['基地被打了，3 个建筑在掉血'])
    assert.deepEqual(wakeSources(agent), [{ kind: 'ra2-wake', frame: 8120, tactic: 'watch_base' }])
    assert.ok(
      agent.session.snapshotEvents().some(event => event.type === 'assistant/message'),
      'the model must have produced a message',
    )
  } finally {
    await ctx.fiber.dispose()
  }
})

test('flush refusal is reported instead of a silent success', async () => {
  const { ctx, agents, port } = await boot({ durable: false })
  const agent = agents[0] as Agent
  try {
    const response = await wake(port, { text: '没有持久化确认' })
    assert.equal(response.status, 200)
    assert.equal(response.body['ok'], false)
    assert.match(String(response.body['error']), /持久化没有确认/)
    // followup still opened a turn; the caller is told delivery was not durable.
    await waitForIdle(agent)
    assert.deepEqual(userTexts(agent), ['没有持久化确认'])
  } finally {
    await ctx.fiber.dispose()
  }
})

test('no candidate Session reports the reason and wakes nothing', async () => {
  const { ctx, agents, port } = await boot({ ra2Tools: false })
  try {
    const response = await wake(port, { text: '无人接收' })
    assert.equal(response.status, 200)
    assert.equal(response.body['ok'], false)
    assert.match(String(response.body['error']), /没有挂/)
    assert.deepEqual(userTexts(agents[0] as Agent), [])
  } finally {
    await ctx.fiber.dispose()
  }
})

test('an explicit session in the body overrides discovery', async () => {
  const { ctx, agents, port } = await boot({ ra2Tools: false })
  const agent = agents[0] as Agent
  try {
    const response = await wake(port, { text: '点名唤醒', session: 'ra2-agent-a' })
    assert.equal(response.status, 200)
    assert.deepEqual(response.body, { ok: true, session: 'ra2-agent-a' })
    await waitForIdle(agent)
    assert.deepEqual(userTexts(agent), ['点名唤醒'])
  } finally {
    await ctx.fiber.dispose()
  }
})

test('a missing session fails with the resolution reason', async () => {
  const { ctx, port } = await boot()
  try {
    const response = await wake(port, { text: '不存在的会话', session: 'no-such-session' })
    assert.equal(response.status, 200)
    assert.equal(response.body['ok'], false)
    assert.match(String(response.body['error']), /not found/)
  } finally {
    await ctx.fiber.dispose()
  }
})

test('the request body is bounded and validated', async () => {
  const { ctx, port } = await boot()
  try {
    const empty = await wake(port, { text: '   ' })
    assert.equal(empty.status, 400)
    assert.equal(empty.body['ok'], false)

    const missing = await wake(port, { frame: 1 })
    assert.equal(missing.status, 400)
    assert.match(String(missing.body['error']), /text/)

    const badFrame = await wake(port, { text: 'x', frame: 1.5 })
    assert.equal(badFrame.status, 400)
    assert.match(String(badFrame.body['error']), /frame/)

    const badJson = await wake(port, '{not json')
    assert.equal(badJson.status, 400)
    assert.match(String(badJson.body['error']), /JSON/)

    const wrongType = await wake(port, { text: 'x' }, { contentType: 'text/plain' })
    assert.equal(wrongType.status, 415)

    const noType = await wake(port, { text: 'x' }, { contentType: null })
    assert.equal(noType.status, 415)

    const wrongMethod = await wake(port, {}, { method: 'GET' })
    assert.equal(wrongMethod.status, 405)

    const oversized = await wake(port, { text: 'x'.repeat(4096) })
    assert.equal(oversized.status, 413)
  } finally {
    await ctx.fiber.dispose()
  }
})

test('the shared secret guards every request when configured', async () => {
  const ctx = new CordisContext()
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  ctx.llm.registerAdapter(['mock'], scriptedAdapter())
  ctx.tools.register(ra2Tool())
  ctx.on('session/flush', () => undefined)
  const agent = await ctx.agentLoop.create(SessionId('ra2-agent-secret'), { provider: 'mock', model: 'mock' })
  ctx.provide('sessionController', { resolveAgent: async () => ({ agent }) } as never)
  ctx.provide('credentials', {
    resolve: async (ref: string) => ref === 'RA2_WAKE_SECRET' ? { value: 's3cret', source: 'env' } : undefined,
  } as never)
  await ctx.plugin(Wake, {
    path: '/ra2/wake',
    maxBodyBytes: 2048,
    mcpServerName: 'ra2',
    fallbackSession: '',
    secretEnv: 'RA2_WAKE_SECRET',
  })
  await ctx.plugin(WebServer, { host: '127.0.0.1', port: 0, compression: 'none' })
  const port = ctx.webServer.port
  try {
    const body = JSON.stringify({ text: '带密钥' })
    const missing = await fetch(`http://127.0.0.1:${String(port)}/ra2/wake`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body,
    })
    assert.equal(missing.status, 401)

    const wrong = await fetch(`http://127.0.0.1:${String(port)}/ra2/wake`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-ra2-wake-secret': 'nope' },
      body,
    })
    assert.equal(wrong.status, 401)

    const right = await fetch(`http://127.0.0.1:${String(port)}/ra2/wake`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-ra2-wake-secret': 's3cret' },
      body,
    })
    assert.equal(right.status, 200)
    assert.deepEqual(await right.json(), { ok: true, session: 'ra2-agent-secret' })
  } finally {
    await ctx.fiber.dispose()
  }
})

test('an unauthenticated route refuses a non-loopback WebServer', () => {
  const ctx = new CordisContext()
  ctx.provide('webServer', { host: '0.0.0.0', register: () => () => undefined } as never)
  assert.throws(
    () => { Wake.apply(ctx, { path: '/ra2/wake', maxBodyBytes: 1024, mcpServerName: 'ra2', fallbackSession: '', secretEnv: '' }) },
    /refuses to serve an unauthenticated wake route/,
  )
  void ctx.fiber.dispose()
})

test('several idle candidates report the ambiguity, and fallbackSession resolves it', async () => {
  const ambiguous = await boot({ count: 2 })
  try {
    const response = await wake(ambiguous.port, { text: '两个候选' })
    assert.equal(response.status, 200)
    assert.equal(response.body['ok'], false)
    assert.match(String(response.body['error']), /ra2-agent-a/)
    assert.match(String(response.body['error']), /ra2-agent-b/)
    for (const agent of ambiguous.agents) assert.deepEqual(userTexts(agent), [])
  } finally {
    await ambiguous.ctx.fiber.dispose()
  }

  const ctx = new CordisContext()
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  ctx.llm.registerAdapter(['mock'], scriptedAdapter())
  ctx.tools.register(ra2Tool())
  ctx.on('session/flush', () => undefined)
  const first = await ctx.agentLoop.create(SessionId('ra2-agent-a'), { provider: 'mock', model: 'mock' })
  await ctx.agentLoop.create(SessionId('ra2-agent-b'), { provider: 'mock', model: 'mock' })
  ctx.provide('sessionController', {
    resolveAgent: async (sessionId: string) => sessionId === 'ra2-agent-a'
      ? { agent: first }
      : { error: { message: `session "${sessionId}" not found` } },
  } as never)
  await ctx.plugin(Wake, { path: '/ra2/wake', maxBodyBytes: 2048, mcpServerName: 'ra2', fallbackSession: 'ra2-agent-a', secretEnv: '' })
  await ctx.plugin(WebServer, { host: '127.0.0.1', port: 0, compression: 'none' })
  try {
    const response = await wake(ctx.webServer.port, { text: '按配置兜底' })
    assert.equal(response.status, 200)
    assert.deepEqual(response.body, { ok: true, session: 'ra2-agent-a' })
    await waitForIdle(first)
    assert.deepEqual(userTexts(first), ['按配置兜底'])
  } finally {
    await ctx.fiber.dispose()
  }
})

test('discovery sees MCP tools registered on the preset scope above the agent', async () => {
  // Production shape: mcp-client is a row of the agent preset, so its tools are
  // registered on the preset scope, which the agent's own scope chains under.
  const ctx = new CordisContext()
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  ctx.llm.registerAdapter(['mock'], scriptedAdapter())
  ctx.on('session/flush', () => undefined)
  const agent = await ctx.agentLoop.create(SessionId('ra2-agent-preset'), { provider: 'mock', model: 'mock' })
  const presetKey = {}
  const presetScope = createScope(ctx, presetKey)
  await presetScope.ctx.plugin({
    name: 'preset-ra2-tools',
    inject: ['tools'],
    apply(scoped: Context) { scoped.tools.register(ra2Tool()) },
  })
  bindScopeParent(agent, presetKey)
  assert.ok(
    ctx.tools.schemas(agent).some(tool => tool.name === 'mcp__ra2__status'),
    'a preset-scoped MCP tool must be visible from the agent scope',
  )
  ctx.provide('sessionController', { resolveAgent: async () => ({ agent }) } as never)
  await ctx.plugin(Wake, { path: '/ra2/wake', maxBodyBytes: 2048, mcpServerName: 'ra2', fallbackSession: '', secretEnv: '' })
  await ctx.plugin(WebServer, { host: '127.0.0.1', port: 0, compression: 'none' })
  try {
    const response = await wake(ctx.webServer.port, { text: 'preset 作用域里的 MCP 工具' })
    assert.equal(response.status, 200)
    assert.deepEqual(response.body, { ok: true, session: 'ra2-agent-preset' })
  } finally {
    await ctx.fiber.dispose()
  }
})

test('the built package mounts through the real Loader', async () => {
  const root = await mkdtemp(join(tmpdir(), 'dsh-ra2-wake-loader-'))
  const configPath = join(root, 'cordis.yml')
  await writeFile(configPath, [
    '- name: fixture-dependencies',
    "- name: '@deepseek-ai/dsh-host-webserver'",
    '  config:',
    "    host: '127.0.0.1'",
    '    port: 0',
    "    compression: 'none'",
    "- name: '@local/ra2-wake'",
    '  config:',
    '    path: /ra2/wake',
    '    maxBodyBytes: 1024',
    '    mcpServerName: ra2',
    "    fallbackSession: ''",
    "    secretEnv: ''",
    '',
  ].join('\n'))

  const followups: { content: readonly unknown[]; source: unknown }[] = []
  let flushes = 0
  const fakeAgent = {
    id: 'fixture-session',
    status: 'idle',
    session: { id: 'fixture-session' },
    followup: (message: { content: readonly unknown[]; source: unknown }) => { followups.push(message) },
  }
  const dependencies = {
    name: 'fixture-dependencies',
    apply(ctx: Context) {
      ctx.provide('agents', { roots: () => [fakeAgent] } as never)
      ctx.provide('tools', { schemas: () => [{ name: 'mcp__ra2__status' }] } as never)
      ctx.provide('sessions', { flush: async () => { flushes += 1; return true } } as never)
      ctx.provide('sessionController', { resolveAgent: async () => ({ agent: fakeAgent }) } as never)
    },
  }

  const context = new CordisContext()
  context.baseUrl = pathToFileURL(root).href + '/'
  try {
    await context.plugin(Loader)
    context.loader.builtins.include = Include
    const modules = new Map<string, unknown>([
      ['fixture-dependencies', dependencies],
      ['@deepseek-ai/dsh-host-webserver', WebServer],
      ['@local/ra2-wake', WakeBuilt],
    ])
    context.loader.internal = {
      version: 'v2',
      async import(specifier: string) {
        if (!modules.has(specifier)) throw new Error(`unexpected Loader import: ${specifier}`)
        return modules.get(specifier)
      },
    } as unknown as NonNullable<typeof context.loader.internal>
    await context.loader.create({
      name: 'cordis:include',
      config: { path: pathToFileURL(configPath).href },
    })
    await context.loader.await()

    const response = await wake(context.webServer.port, { text: '经 Loader 装载', frame: 42, tactic: 'watch_base' })
    assert.equal(response.status, 200)
    assert.deepEqual(response.body, { ok: true, session: 'fixture-session' })
    assert.equal(flushes, 1)
    assert.equal(followups.length, 1)
    assert.deepEqual(followups[0]?.content, [{ type: 'text', text: '经 Loader 装载' }])
    assert.deepEqual(followups[0]?.source, { kind: 'ra2-wake', frame: 42, tactic: 'watch_base' })
  } finally {
    await context.fiber.dispose()
    await rm(root, { recursive: true, force: true })
  }
})

test('the Loader rejects an invalid route path instead of registering it', async () => {
  const root = await mkdtemp(join(tmpdir(), 'dsh-ra2-wake-loader-bad-'))
  const configPath = join(root, 'cordis.yml')
  await writeFile(configPath, [
    '- name: fixture-dependencies',
    "- name: '@deepseek-ai/dsh-host-webserver'",
    '  config:',
    "    host: '127.0.0.1'",
    '    port: 0',
    "    compression: 'none'",
    "- name: '@local/ra2-wake'",
    '  config:',
    '    path: ra2/wake',
    '    maxBodyBytes: 1024',
    '    mcpServerName: ra2',
    "    fallbackSession: ''",
    "    secretEnv: ''",
    '',
  ].join('\n'))

  const dependencies = {
    name: 'fixture-dependencies',
    apply(ctx: Context) {
      ctx.provide('agents', { roots: () => [] } as never)
      ctx.provide('tools', { schemas: () => [] } as never)
      ctx.provide('sessions', { flush: async () => true } as never)
      ctx.provide('sessionController', { resolveAgent: async () => ({ error: { message: 'none' } }) } as never)
    },
  }

  const context = new CordisContext()
  context.baseUrl = pathToFileURL(root).href + '/'
  try {
    await context.plugin(Loader)
    context.loader.builtins.include = Include
    const modules = new Map<string, unknown>([
      ['fixture-dependencies', dependencies],
      ['@deepseek-ai/dsh-host-webserver', WebServer],
      ['@local/ra2-wake', WakeBuilt],
    ])
    context.loader.internal = {
      version: 'v2',
      async import(specifier: string) {
        if (!modules.has(specifier)) throw new Error(`unexpected Loader import: ${specifier}`)
        return modules.get(specifier)
      },
    } as unknown as NonNullable<typeof context.loader.internal>
    await context.loader.create({
      name: 'cordis:include',
      config: { path: pathToFileURL(configPath).href },
    })
    await context.loader.await()
    const response = await fetch(`http://127.0.0.1:${String(context.webServer.port)}/ra2/wake`, { method: 'POST' })
    assert.equal(response.status, 404)
  } finally {
    await context.fiber.dispose()
    await rm(root, { recursive: true, force: true })
  }
})
