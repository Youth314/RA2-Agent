/**
 * ra2-players 测试：真实的 Cordis 组合（ToolRuntime + AgentRegistry + AgentLoop +
 * 真实 scope 链），只有 `ctx.subagents` 与 MCP 客户端插件是替身——不替身就会真去
 * 起 `python3 -m ra2agent.mcp`，那要动游戏。
 *
 * Run: `TSX_TSCONFIG_PATH=./tsconfig.test.json node --import tsx/esm tests/players.test.ts`
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
import type { Agent, AgentHandle } from '@deepseek-ai/dsh-agent'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import LlmRuntime from '@deepseek-ai/dsh-llm'
import { MessageId, ToolCallId } from '@deepseek-ai/dsh-llm'
import type { Config as McpClientConfig } from '@deepseek-ai/dsh-mcp-client'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionStore from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import { bindScopeParent, createScope } from '@deepseek-ai/dsh-scope'
import type { Scope } from '@deepseek-ai/dsh-scope'
import { applyChildComposition } from '@deepseek-ai/dsh-subagent'
import type { ContinuableStartSpec } from '@deepseek-ai/dsh-subagent'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime, { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import { MockAdapter, textResponse } from '/home/youthz/deepseek-harness/packages/core/agent-loop/tests/mock-adapter.ts'
import * as Players from '../src/index.ts'
import { PlayerClaims, playerServerName, playerToolName } from '../src/players.ts'
import type { PlayerClientPlugin } from '../src/players.ts'

/** 一份两方的名册，跟 `config/match.json` 同形。 */
function rosterOf(names: readonly string[]): string {
  return JSON.stringify({
    map: 'spawnmap.ini',
    ready_timeout: 120.0,
    launch_gap: 12.0,
    players: names.map((name, index) => ({
      name,
      game_dir: `D:\\Games\\ra2probe-${String(index)}`,
      probe_port: 14521 + index,
      side: index % 2,
      color: index + 1,
    })),
  })
}

/** 一条注册在某个 scope 里的假 MCP 工具。 */
function fixtureTool(name: string) {
  return defineContentToolFixture({
    name,
    description: name,
    parameters: {},
    execute: async () => [{ type: 'text', text: 'ok' }],
  })
}

/** 假 MCP 客户端：按 serverName 注册一条 `<前缀>status`，跟真的一样落在玩家 scope 的 own 层。 */
function fakeClient(): PlayerClientPlugin {
  return {
    name: 'fixture-mcp-client',
    inject: ['tools'],
    apply(clientCtx: Context, config: McpClientConfig) {
      assert.equal(config.transport, 'stdio')
      if (config.transport !== 'stdio') return
      clientCtx.tools.register(fixtureTool(`mcp__${config.serverName}__status`))
    },
  }
}

interface Started {
  readonly spec: ContinuableStartSpec
  readonly handle: AgentHandle
}

interface BootOptions {
  /** 名册文本；不给就用两方默认名册。 */
  readonly roster?: string
  /** 直接用这个路径当 rosterPath（用来验读不了的情况）。 */
  readonly rosterPath?: string
  /** 祖先 scope（父 preset 那一层）里有没有 `mcp__ra2__status`；默认有。 */
  readonly inheritedTools?: boolean
  /** `ctx.agents.create` 返回之后、`startContinuable` 返回之前的观察点。 */
  readonly onChildCreated?: (ctx: Context, spec: ContinuableStartSpec, child: Agent) => void
  /** 替身 provider 声称支持哪些能力；默认支持 toolFilter。 */
  readonly toolFilterCapable?: boolean
}

interface Booted {
  readonly ctx: Context
  readonly rosterPath: string
  readonly ancestorKey: object
  /** 模拟父 preset 那一层的 scope：测试可以往它里面再注册工具。 */
  readonly ancestorScope: Scope
  readonly started: Started[]
  readonly cleanup: () => Promise<void>
}

/** 某个 scope 看得见的工具名。 */
function visibleTools(ctx: Context, scope: object): string[] {
  return ctx.tools.schemas(scope).map(schema => schema.name).sort()
}

/** 组装一局：真实 agent 栈 + 祖先 scope + 替身的 subagents。 */
async function boot(options: BootOptions = {}): Promise<Booted> {
  const root = await mkdtemp(join(tmpdir(), 'dsh-ra2-players-'))
  const rosterPath = options.rosterPath ?? join(root, 'match.json')
  if (options.rosterPath === undefined) {
    await writeFile(rosterPath, options.roster ?? rosterOf(['Alpha', 'Beta']))
  }

  const ctx = new CordisContext()
  await ctx.plugin(LlmRuntime)
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(AgentRegistry)
  await ctx.plugin(AgentLoop, { agents: [] })
  ctx.llm.registerAdapter(['mock'], new MockAdapter([
    textResponse('待命'), textResponse('待命'), textResponse('待命'),
  ]))

  // 祖先 scope：父 preset 里那一行 mcp-ra2 留下的工具就在这一层，子 agent 继承它。
  // 必须在一个声明了 inject 的插件里建，scope 的 ctx 才拿得到 `tools`。
  const ancestorKey = { kind: 'preset-generation' }
  let ancestorScope: Scope | undefined
  await ctx.plugin({
    name: 'fixture-ancestor-scope',
    inject: ['tools'],
    apply: (fixtureCtx: Context) => {
      const scope = createScope(fixtureCtx, ancestorKey)
      ancestorScope = scope
      if (options.inheritedTools !== false) scope.ctx.tools.register(fixtureTool('mcp__ra2__status'))
    },
  })
  assert.ok(ancestorScope !== undefined, '祖先 scope 应该在 boot 里就建好')

  const started: Started[] = []
  const provider = { name: 'fixture-provider', capabilities: { toolFilter: options.toolFilterCapable ?? true } }
  const subagents = {
    getProvider: (name: string) => (name === 'spawn' ? provider : undefined),
    async startContinuable(spec: ContinuableStartSpec) {
      // 顺序陷阱：agent/created 在这个 await 里面就触发，此刻认领必须已经写好。
      const handle = await ctx.agents.create({
        sessionId: spec.childId as SessionId,
        parentAgent: spec.request.parent,
        agentOptions: { provider: 'mock', model: 'mock' },
        // 模拟子 agent 继承父的 preset：把它的 scope 挂到祖先那一层下面。
        setup: (_childCtx: Context, child: Agent) => { bindScopeParent(child, ancestorKey) },
      })
      started.push({ spec, handle })
      options.onChildCreated?.(ctx, spec, handle.agent)
      return { childId: handle.agent.id, messageId: MessageId(`m-${String(started.length)}`) }
    },
  }
  ctx.provide('subagents', subagents as never)

  return {
    ctx,
    rosterPath,
    ancestorKey,
    ancestorScope,
    started,
    cleanup: async () => {
      await ctx.fiber.dispose()
      await rm(root, { recursive: true, force: true })
    },
  }
}

/** 在一个隔离的插件 fiber 里装载本插件，客户端插件可替换。 */
async function mount(
  ctx: Context,
  config: Players.Config,
  client: PlayerClientPlugin = fakeClient(),
): Promise<void> {
  await ctx.plugin({
    name: 'fixture-ra2-players',
    inject: ['tools', 'subagents', 'agents'],
    apply: (pluginCtx: Context) => { Players.mountPlayers(pluginCtx, config, client) },
  })
}

/** 建一个主持 agent 当调用者，并把它挂到祖先 scope 下面（等价于它加入了 ra2 preset）。 */
async function createLead(ctx: Context, ancestorKey: object): Promise<Agent> {
  const lead = await ctx.agentLoop.create(SessionId('lead'), { provider: 'mock', model: 'mock' })
  bindScopeParent(lead, ancestorKey)
  return lead
}

/** 调用一次已注册的 `play_as_*` 工具；失败时把模型看到的那段文本抛出来。 */
async function callPlay(ctx: Context, caller: Agent, toolName: string, task: string): Promise<string> {
  const result = await ctx.tools.execute({
    callId: ToolCallId(`call-${toolName}-${task}`),
    name: toolName,
    arguments: { description: '跑一局', task },
    agent: caller,
    signal: new AbortController().signal,
  })
  const text = result.content.flatMap(block => block.type === 'text' ? [block.text] : []).join('\n')
  if (result.isError) throw new Error(text)
  return text
}

test('名册读不了时插件加载就失败，不静默注册零个工具', async () => {
  const b = await boot({ rosterPath: '/nonexistent/ra2/match.json' })
  try {
    await assert.rejects(mount(b.ctx, { rosterPath: b.rosterPath }), /名册 .*读不了/)
    assert.deepEqual(b.ctx.tools.schemas(), [], '加载失败时不该留下任何工具')
  } finally {
    await b.cleanup()
  }
})

test('名册内容不合法时插件加载就失败', async () => {
  const empty = await boot({ roster: '{"players": []}' })
  try {
    await assert.rejects(mount(empty.ctx, { rosterPath: empty.rosterPath }), /players 是空的/)
  } finally {
    await empty.cleanup()
  }

  const duplicated = await boot({ roster: rosterOf(['Alpha', 'alpha']) })
  try {
    await assert.rejects(mount(duplicated.ctx, { rosterPath: duplicated.rosterPath }), /同一个工具名/)
  } finally {
    await duplicated.cleanup()
  }
})

test('玩家名里有非 [a-z0-9_] 字符时插件加载就失败', async () => {
  const b = await boot({ roster: rosterOf(['Alpha-1', 'Beta']) })
  try {
    await assert.rejects(mount(b.ctx, { rosterPath: b.rosterPath }), /含 \[a-z0-9_\] 之外的字符/)
    assert.deepEqual(b.ctx.tools.schemas(), [])
  } finally {
    await b.cleanup()
  }
})

test('名册读得动时每个玩家各一个 play_as_<名字> 工具', async () => {
  const b = await boot()
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath })
    assert.deepEqual(
      b.ctx.tools.schemas().map(schema => schema.name).sort(),
      [playerToolName('Alpha'), playerToolName('Beta')].sort(),
    )
    assert.equal(playerToolName('Alpha'), 'play_as_alpha')
    assert.equal(playerServerName('Beta'), 'ra2_beta')
  } finally {
    await b.cleanup()
  }
})

test('认领写在 startContinuable 之前：agent/created 触发时子 agent 已经挂好了', async () => {
  const seen: string[][] = []
  const b = await boot({
    onChildCreated: (ctx, _spec, child) => { seen.push(visibleTools(ctx, child)) },
  })
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath })
    const lead = await createLead(b.ctx, b.ancestorKey)
    await callPlay(b.ctx, lead, playerToolName('Alpha'), '守住左路')

    // 观察点在真实 startContinuable 内部：agent/created 已经在 ctx.agents.create 里
    // 跑过了。那一步能挂上客户端，只可能是因为认领在调用 startContinuable 之前就写好了。
    assert.equal(seen.length, 1)
    const names = seen[0] ?? []
    assert.ok(names.includes('mcp__ra2_alpha__status'), `子 agent 该有自己的工具，实际 ${names.join(',')}`)
    assert.ok(!names.includes('mcp__ra2__status'), '子 agent 不该继承那份没带 --player 的客户端工具')
  } finally {
    await b.cleanup()
  }
})

test('重复调用同一个玩家被拒绝，原来的 agent 结算后才放行', async () => {
  const b = await boot()
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath })
    const lead = await createLead(b.ctx, b.ancestorKey)
    await callPlay(b.ctx, lead, playerToolName('Alpha'), '第一局')
    assert.equal(b.started.length, 1)
    const first = b.started[0]
    assert.ok(first !== undefined)

    await assert.rejects(
      callPlay(b.ctx, lead, playerToolName('Alpha'), '第二局'),
      /已经有一个在跑的玩家 agent/,
    )
    assert.equal(b.started.length, 1, '被拒绝的调用不该建出第二个同玩家 agent')

    // 另一个玩家不受影响。
    await callPlay(b.ctx, lead, playerToolName('Beta'), '打右边')
    assert.equal(b.started.length, 2)

    // 第一个 agent 结算（被处置）之后，同一个玩家可以重新认领，拿到新的 id。
    await first.handle.dispose()
    await callPlay(b.ctx, lead, playerToolName('Alpha'), '第三局')
    assert.equal(b.started.length, 3)
    assert.notEqual(b.started[2]?.spec.childId, first.spec.childId)
  } finally {
    await b.cleanup()
  }
})

test('子 agent 只看得见自己那一份客户端，上层那份被 deny 掉', async () => {
  const b = await boot()
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath })
    const lead = await createLead(b.ctx, b.ancestorKey)
    await callPlay(b.ctx, lead, playerToolName('Alpha'), '守住左路')
    await callPlay(b.ctx, lead, playerToolName('Beta'), '打右边')

    const alpha = b.started[0]?.handle.agent
    const beta = b.started[1]?.handle.agent
    assert.ok(alpha !== undefined && beta !== undefined)

    assert.deepEqual(
      visibleTools(b.ctx, alpha).filter(name => name.startsWith('mcp__')),
      ['mcp__ra2_alpha__status'],
    )
    assert.deepEqual(
      visibleTools(b.ctx, beta).filter(name => name.startsWith('mcp__')),
      ['mcp__ra2_beta__status'],
    )
    // 祖先那一层（主持 agent 继承的那份）照旧。
    assert.ok(visibleTools(b.ctx, b.ancestorKey).includes('mcp__ra2__status'))
    // 工具表里没有，按名字也解析不到。
    assert.equal(b.ctx.tools.get('mcp__ra2__status', alpha), undefined)
    assert.equal(b.ctx.tools.get('mcp__ra2_alpha__status', beta), undefined)
  } finally {
    await b.cleanup()
  }
})

test('deny 之后才出现的继承工具，由 tools/execute 守卫按前缀拒绝', async () => {
  const b = await boot()
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath })
    const lead = await createLead(b.ctx, b.ancestorKey)
    await callPlay(b.ctx, lead, playerToolName('Alpha'), '守住左路')
    const alpha = b.started[0]?.handle.agent
    assert.ok(alpha !== undefined)
    assert.deepEqual(
      visibleTools(b.ctx, alpha).filter(name => name.startsWith('mcp__')),
      ['mcp__ra2_alpha__status'],
    )

    // 挂载之后上层那份客户端又注册了一条（比如重连之后重新列工具）：它不在
    // 建立时算出的 deny 名单里，于是落到守卫上。
    b.ancestorScope.ctx.tools.register(fixtureTool('mcp__ra2__late'))

    const denied = await b.ctx.tools.execute({
      callId: ToolCallId('call-late'),
      name: 'mcp__ra2__late',
      arguments: {},
      agent: alpha,
      signal: new AbortController().signal,
    })
    assert.equal(denied.isError, true)
    assert.match(
      denied.content.flatMap(block => block.type === 'text' ? [block.text] : []).join('\n'),
      /不属于本玩家，已拒绝/,
    )
  } finally {
    await b.cleanup()
  }
})

test('看不见上层那份客户端时拒绝开工（除非配成没有这一层）', async () => {
  const missing = await boot({ inheritedTools: false })
  try {
    await mount(missing.ctx, { rosterPath: missing.rosterPath })
    const lead = await createLead(missing.ctx, missing.ancestorKey)
    await assert.rejects(
      callPlay(missing.ctx, lead, playerToolName('Alpha'), '守住左路'),
      /看不到任何 mcp__ra2__\* 工具/,
    )
    assert.equal(missing.started.length, 0, '被拒绝时不该建出子 agent')
  } finally {
    await missing.cleanup()
  }

  const absent = await boot({ inheritedTools: false })
  try {
    await mount(absent.ctx, { rosterPath: absent.rosterPath, inheritedServerName: '' })
    const lead = await createLead(absent.ctx, absent.ancestorKey)
    await callPlay(absent.ctx, lead, playerToolName('Alpha'), '守住左路')
    assert.equal(absent.started.length, 1)
    const alpha = absent.started[0]?.handle.agent
    assert.ok(alpha !== undefined)
    assert.deepEqual(
      visibleTools(absent.ctx, alpha).filter(name => name.startsWith('mcp__')),
      ['mcp__ra2_alpha__status'],
    )
  } finally {
    await absent.cleanup()
  }
})

test('认领表：先写后建、活着就拒、失败回滚', () => {
  const claims = new PlayerClaims()
  const childId = SessionId('child-1')
  assert.equal(claims.playerOf(childId), undefined)

  claims.claim('Alpha', childId, () => false)
  assert.equal(claims.playerOf(childId), 'Alpha')

  // 还没活着的旧认领会被顶替。
  claims.claim('Alpha', SessionId('child-2'), () => false)
  assert.equal(claims.playerOf(SessionId('child-2')), 'Alpha')

  // 活着的就会被拒。
  assert.throws(
    () => { claims.claim('Alpha', SessionId('child-3'), candidate => candidate === SessionId('child-2')) },
    /已经有一个在跑的玩家 agent/,
  )

  // 建立失败时回滚。
  claims.release(SessionId('child-2'))
  assert.equal(claims.playerOf(SessionId('child-2')), undefined)
})

test('真 Loader 里装载：Config 默认值生效，坏名册让这一行加载不出来', async () => {
  const root = await mkdtemp(join(tmpdir(), 'dsh-ra2-players-loader-'))
  const good = join(root, 'match.json')
  await writeFile(good, rosterOf(['Alpha', 'Beta']))

  /** 只提供 tools / subagents / agents 的底座；名册路径由参数决定。 */
  const dependencies = {
    name: 'fixture-dependencies',
    inject: ['tools'],
    apply(depsCtx: Context) {
      depsCtx.provide('subagents', {} as never)
      depsCtx.provide('agents', { get: () => undefined } as never)
    },
  }

  /** 用真 Loader 加载一行 `@local/ra2-players`，返回那条行是否装出了工具。 */
  async function loadRow(rosterPath: string): Promise<string[]> {
    const configPath = join(root, `cordis-${String(rosterPath.length)}-${rosterPath.includes('missing') ? 'bad' : 'ok'}.yml`)
    await writeFile(configPath, [
      '- name: fixture-dependencies',
      "- name: '@local/ra2-players'",
      '  config:',
      `    rosterPath: ${rosterPath}`,
      '',
    ].join('\n'))

    const context = new CordisContext()
    context.baseUrl = pathToFileURL(root).href + '/'
    try {
      await context.plugin(LlmRuntime)
      await context.plugin(SystemPrompt, {})
      await context.plugin(ToolRuntime)
      await context.plugin(Loader)
      context.loader.builtins.include = Include
      const modules = new Map<string, unknown>([
        ['fixture-dependencies', dependencies],
        ['@local/ra2-players', Players],
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
      return context.tools.schemas().map(schema => schema.name).sort()
    } finally {
      await context.fiber.dispose()
    }
  }

  try {
    assert.deepEqual(await loadRow(good), [playerToolName('Alpha'), playerToolName('Beta')].sort())
    assert.deepEqual(await loadRow(join(root, 'missing.json')), [], '名册读不了时不该注册任何工具')
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test('真 applyChildComposition：player 的 toolFilter 让继承的 mcp__ra2__* 真的消失', async () => {
  const b = await boot()
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath })
    const lead = await createLead(b.ctx, b.ancestorKey)

    // 与 subagent-in-process-driver / continuation-activation 给子 agent 跑的是同一个
    // 函数、同一份 composition；这里直接把 driver 会传的 toolFilter 喂进去。
    await b.ctx.plugin({
      name: 'fixture-child-composition',
      inject: ['tools', 'systemPrompt'],
      apply: (childCtx: Context) => {
        const childKey = { kind: 'child-agent' }
        const scope = createScope(childCtx, childKey)
        bindScopeParent(childKey, b.ancestorKey)
        assert.ok(visibleTools(b.ctx, childKey).includes('mcp__ra2__status'), '建子 agent 前它继承得到上层那份')
        applyChildComposition(scope.ctx, lead, { toolFilter: { deny: ['mcp__ra2__status'] } })
        assert.ok(!visibleTools(b.ctx, childKey).includes('mcp__ra2__status'), 'deny 之后子 agent 看不到')
        assert.ok(visibleTools(b.ctx, b.ancestorKey).includes('mcp__ra2__status'), '祖先那一层不受影响')
      },
    })
  } finally {
    await b.cleanup()
  }
})

test('provider 不支持 toolFilter 时拒绝开工，不留一条没有隔离的路', async () => {
  const b = await boot({ toolFilterCapable: false })
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath })
    const lead = await createLead(b.ctx, b.ancestorKey)
    await assert.rejects(
      callPlay(b.ctx, lead, playerToolName('Alpha'), '守住左路'),
      /不支持 toolFilter/,
    )
    assert.equal(b.started.length, 0)
  } finally {
    await b.cleanup()
  }
})

test('玩家客户端的命令行带 --player 与 --wake-session <childId>', async () => {
  const b = await boot()
  const configs: McpClientConfig[] = []
  try {
    await mount(b.ctx, { rosterPath: b.rosterPath }, {
      name: 'fixture-mcp-client',
      inject: ['tools'],
      apply: (clientCtx: Context, config: McpClientConfig) => {
        configs.push(config)
        if (config.transport !== 'stdio') return
        clientCtx.tools.register(fixtureTool(`mcp__${config.serverName}__status`))
      },
    })
    const lead = await createLead(b.ctx, b.ancestorKey)
    await callPlay(b.ctx, lead, playerToolName('Alpha'), '守住左路')
    await callPlay(b.ctx, lead, playerToolName('Beta'), '打右边')

    const childIds = b.started.map(started => String(started.spec.childId))
    assert.equal(configs.length, 2)
    const first = configs[0]
    const second = configs[1]
    assert.ok(first !== undefined)
    assert.ok(second !== undefined)
    if (first.transport !== 'stdio' || second.transport !== 'stdio') {
      throw new Error('玩家客户端必须是 stdio 传输')
    }
    assert.deepEqual(first.args, [
      '-m', 'ra2agent.mcp',
      '--roster', b.rosterPath,
      '--player', 'Alpha',
      '--wake-session', childIds[0],
    ])
    assert.deepEqual(second.args, [
      '-m', 'ra2agent.mcp',
      '--roster', b.rosterPath,
      '--player', 'Beta',
      '--wake-session', childIds[1],
    ])
    // 两份配置是两个不同的 serverName，工具名不会撞。
    assert.equal(first.serverName, 'ra2_alpha')
    assert.equal(second.serverName, 'ra2_beta')
    assert.equal(first.cwd, '/home/youthz/ra2-agent')
    assert.equal(first.env['PYTHONPATH'], '/home/youthz/ra2-agent/src')
  } finally {
    await b.cleanup()
  }
})
