<!-- 首页：六屏整页滑动呈现（滚轮 / 触摸 / 键盘 / 圆点导航），
     每屏一个独立强调色，右侧以真实产品 UI 模拟代替抽象功能卡片 -->
<template>
  <div class="home-page" ref="containerRef">
    <!-- 屏1：Hero -->
    <section ref="heroSectionRef" class="slide slide-hero" :class="{ 'is-active': currentIndex === 0 }">
      <!-- 静态渐变背景：顶部光束 + 三枚色斑（借鉴 Nexus aurora 光效，不做动画） -->
      <div class="hero-aurora" aria-hidden="true">
        <div class="aurora-blob blob-blue"></div>
        <div class="aurora-blob blob-violet"></div>
        <div class="aurora-blob blob-cyan"></div>
      </div>
      <div class="slide-inner hero-inner">
        <!-- ═══ 首屏动态标识：三路光带汇聚 → 玻璃节点（定稿主标）→ 三路发散 ═══
             摘取自 docs/assets/参考的首页组件.html 的 living mark 部分：
             流光 SVG + 玻璃节点 + 鼠标视差；远程定稿图换成本地 logo1（logo-mark.png）。 -->
        <div class="hero-mark" aria-hidden="true">
          <div class="mark-flow-wrap">
            <svg class="mark-flow" viewBox="0 0 1240 440" preserveAspectRatio="xMidYMid meet">
              <defs>
                <linearGradient id="markFlowGrad" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1240" y2="0">
                  <stop offset="0" stop-color="#7FA9EC"/>
                  <stop offset="0.46" stop-color="#A9A4E9"/>
                  <stop offset="1" stop-color="#8ED6C8"/>
                </linearGradient>
                <linearGradient id="markPulseGrad" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1240" y2="0">
                  <stop offset="0" stop-color="#C6DCF6"/>
                  <stop offset="0.46" stop-color="#DAD6F6"/>
                  <stop offset="1" stop-color="#C6EBE2"/>
                </linearGradient>
              </defs>
              <g class="mark-lanes">
                <g style="--phase: 0s">
                  <path class="rb-bed-halo" d="M -60 62 C 170 62, 320 150, 525 168 L 715 168 C 920 150, 1080 56, 1300 48"/>
                  <path class="rb-bed" d="M -60 62 C 170 62, 320 150, 525 168 L 715 168 C 920 150, 1080 56, 1300 48"/>
                  <path class="rb-pulse rb-halo" d="M -60 62 C 170 62, 320 150, 525 168 L 715 168 C 920 150, 1080 56, 1300 48"/>
                  <path class="rb-pulse rb-beam" d="M -60 62 C 170 62, 320 150, 525 168 L 715 168 C 920 150, 1080 56, 1300 48"/>
                  <path class="rb-pulse rb-head" d="M -60 62 C 170 62, 320 150, 525 168 L 715 168 C 920 150, 1080 56, 1300 48"/>
                </g>
                <g style="--phase: -1s">
                  <path class="rb-bed-halo" d="M -60 220 C 200 220, 350 220, 525 220 L 715 220 C 940 220, 1100 220, 1300 220"/>
                  <path class="rb-bed" d="M -60 220 C 200 220, 350 220, 525 220 L 715 220 C 940 220, 1100 220, 1300 220"/>
                  <path class="rb-pulse rb-halo" d="M -60 220 C 200 220, 350 220, 525 220 L 715 220 C 940 220, 1100 220, 1300 220"/>
                  <path class="rb-pulse rb-beam" d="M -60 220 C 200 220, 350 220, 525 220 L 715 220 C 940 220, 1100 220, 1300 220"/>
                  <path class="rb-pulse rb-head" d="M -60 220 C 200 220, 350 220, 525 220 L 715 220 C 940 220, 1100 220, 1300 220"/>
                </g>
                <g style="--phase: -2s">
                  <path class="rb-bed-halo" d="M -60 378 C 170 378, 320 290, 525 272 L 715 272 C 920 290, 1080 384, 1300 392"/>
                  <path class="rb-bed" d="M -60 378 C 170 378, 320 290, 525 272 L 715 272 C 920 290, 1080 384, 1300 392"/>
                  <path class="rb-pulse rb-halo" d="M -60 378 C 170 378, 320 290, 525 272 L 715 272 C 920 290, 1080 384, 1300 392"/>
                  <path class="rb-pulse rb-beam" d="M -60 378 C 170 378, 320 290, 525 272 L 715 272 C 920 290, 1080 384, 1300 392"/>
                  <path class="rb-pulse rb-head" d="M -60 378 C 170 378, 320 290, 525 272 L 715 272 C 920 290, 1080 384, 1300 392"/>
                </g>
              </g>
            </svg>
            <div class="mark-node-parallax">
              <div class="mark-node">
                <span class="mark-sheen"></span>
                <img class="mark-node-logo" :src="logoMark" alt=""/>
              </div>
            </div>
          </div>
          <div class="mark-labels"><span>IN</span><span>ROUTE</span><span>OUT</span></div>
        </div>
        <p class="slide-eyebrow">AGENTIC API · 大模型中转站</p>
        <h1 class="hero-title">由 Agent 自主运营维护的<br/><span class="hero-title-key">新一代智能 API 中转站</span>
        </h1>
        <p class="hero-desc">
          上游渠道自动巡检监测・下游 OpenAI 接口对外兼容
        </p>
        <div class="hero-actions">
          <a-button type="primary" @click="goToModelsPage">查看模型广场</a-button>
          <a-button @click="handleStart">立即开始使用</a-button>
        </div>

        <!-- 数据速览：等宽数字 + 分隔线，贴近控制台质感 -->
        <div class="hero-metrics">
          <div class="hero-metric">
            <span class="hero-metric-value">{{ modelListStore.totalModelNumber }}</span>
            <span class="hero-metric-label">可用模型</span>
          </div>
          <div class="hero-metric">
            <span class="hero-metric-value">{{ modelListStore.freeModelNumber }}</span>
            <span class="hero-metric-label">免费模型</span>
          </div>
          <div class="hero-metric">
            <span class="hero-metric-value">100%</span>
            <span class="hero-metric-label">OpenAI 兼容</span>
          </div>
          <div class="hero-metric">
            <span class="hero-metric-value">7 × 24</span>
            <span class="hero-metric-label">多渠道容灾</span>
          </div>
        </div>
      </div>
      <div class="scroll-hint" @click="scrollToPage(1)">
        <icon-down/>
      </div>
    </section>

    <!-- 屏2：模型广场（真实模型卡片模拟） -->
    <section class="slide slide-models" :class="{ 'is-active': currentIndex === 1 }">
      <div class="slide-inner split">
        <div class="slide-copy">
          <p class="slide-eyebrow eyebrow-blue">01 · 模型广场</p>
          <h2 class="slide-title">海量模型，低价调用</h2>
          <p class="slide-desc">多款免费模型开箱即用，配套精细化用量监控。三段式定价（输入 / 缓存 /
            输出），有效控制调用开销。</p>
          <a-button type="primary" @click="goToModelsPage">
            进入模型广场
            <template #icon>
              <icon-right/>
            </template>
          </a-button>
        </div>
        <div class="slide-visual">
          <div class="mock-card-grid">
            <!-- 展示卡固定 8 张（4 行 2 列）：置顶模型优先，不足 8 个再从其余启用的模型补齐 -->
            <div v-for="m in showcaseModels" :key="m.name" class="mock-model-card">
              <div class="mock-model-head">
                <LobeIcon :name="m.icon" :fallback="m.name" :size="25"/>
                <span class="mock-model-name">{{ m.name }}</span>
                <span class="mock-model-tag" :class="m.group === 'free' ? 'tag-free' : 'tag-vip'">
                  {{ m.group === 'free' ? '免费' : 'VIP' }}
                </span>
              </div>
              <div class="mock-model-price">
                <span>输入 <b>¥{{ m.inputPrice }}</b></span>
                <span>缓存 <b>¥{{ m.cachePrice }}</b></span>
                <span>输出 <b>¥{{ m.outputPrice }}</b></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 屏3：模型工坊（对话面板模拟） -->
    <section class="slide slide-studio" :class="{ 'is-active': currentIndex === 2 }">
      <div class="slide-inner split split-reverse">
        <div class="slide-copy">
          <p class="slide-eyebrow eyebrow-violet">02 · 模型工坊</p>
          <h2 class="slide-title">先试效果，再上生产</h2>
          <p class="slide-desc">流式输出与思维链实时预览，参数灵活可调，所选模型即线上真实调用通道。</p>
          <a-button type="primary" @click="goToStudioPage">
            打开模型工坊
            <template #icon>
              <icon-right/>
            </template>
          </a-button>
        </div>
        <div class="slide-visual">
          <div class="mock-chat">
            <div class="mock-chat-row mock-chat-user">我在接入后想切换模型，需要修改业务代码吗？</div>
            <div class="mock-chat-row mock-chat-ai">
              <!-- 思维链折叠块：对齐工坊页面 .reasoning-block 的橙色配色 -->
              <div class="mock-reasoning">
                <div class="mock-reasoning-header">
                  <icon-right class="mock-reasoning-arrow"/>
                  <span>🧠 思考中 ...</span>
                </div>
                <div class="mock-reasoning-text">
                  用户关注模型切换的代码侵入性。AgenticAPI 网关已实现 OpenAI
                  协议全字段映射，鉴权绑定租户而非单一模型，核心请求零修改。但需排查两个边界：Function Calling schema
                  格式是否兼容、目标模型 max_tokens 上限是否满足当前截断策略。结论：仅改 model 字段即可，附带兼容性提示。
                </div>
              </div>
              <div class="mock-chat-text">
                核心业务代码无需修改。只需将请求中的 <code>model</code> 参数替换为目标模型名，鉴权方式和 SDK 调用保持完全兼容。<br/><br/>
                有两点建议留意：若使用了 Function Calling，请确认目标模型支持相同的工具定义格式；若依赖较长上下文，切换后建议验证
                max_tokens 上限是否符合预期。<span class="mock-caret"></span>
              </div>
            </div>
            <div class="mock-chat-meta">
              <span>step-3.7-flash |</span>
              <span>temperature 0.7 |</span>
              <span>耗时 1.2s · 72 tokens/s</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 屏4：监控面板（统计 + 柱状图模拟） -->
    <section class="slide slide-monitor" :class="{ 'is-active': currentIndex === 3 }">
      <div class="slide-inner split">
        <div class="slide-copy">
          <p class="slide-eyebrow eyebrow-green">03 · 监控面板</p>
          <h2 class="slide-title">每次调用，有迹可循</h2>
          <p class="slide-desc">
            对话数据、调用日志与用量看板三视图联动，
            时间范围与粒度自由组合，费用与耗时一目了然。
          </p>
          <a-button type="primary" @click="goToMonitorPage">
            进入监控面板
            <template #icon>
              <icon-right/>
            </template>
          </a-button>
        </div>
        <div class="slide-visual">
          <!-- 4 张统计卡片（2×2）：单卡样式复用监控页全局 .stat-card 配色 -->
          <div class="mock-stat-grid">
            <div class="stat-card">
              <div class="stat-label">输入 token</div>
              <div class="stat-value stat-value-brand">8.42M</div>
            </div>
            <div class="stat-card stat-accent-gold">
              <div class="stat-label">缓存 token</div>
              <div class="stat-value stat-value-brand">6.16M</div>
            </div>
            <div class="stat-card stat-accent-cyan">
              <div class="stat-label">输出 token</div>
              <div class="stat-value stat-value-brand">3.27M</div>
            </div>
            <div class="stat-card stat-accent-orange">
              <div class="stat-label">区间费用</div>
              <div class="stat-value stat-value-brand">¥18.62</div>
            </div>
          </div>
          <!-- 调用次数折线图：直接复用监控页 LineChart 组件，配色与结构完全一致 -->
          <div class="mock-chart-card">
            <div class="mock-chart-title">调用次数</div>
            <LineChart :x-data="monitorXData" :series="monitorSeries" unit="次" renderer="svg"/>
          </div>
        </div>
      </div>
    </section>

    <!-- 屏5：控制台（密钥 / 渠道管理模拟） -->
    <section class="slide slide-console" :class="{ 'is-active': currentIndex === 4 }">
      <div class="slide-inner split split-reverse">
        <div class="slide-copy">
          <p class="slide-eyebrow eyebrow-orange">04 · 控制台</p>
          <h2 class="slide-title">多组凭证，统一管控</h2>
          <p class="slide-desc">API密钥创建、吊销与余额数据集中汇总，多凭证统一维护，权限与资产状态一目了然。</p>
          <a-button type="primary" @click="goToDashboardPage">
            进入控制台
            <template #icon>
              <icon-right/>
            </template>
          </a-button>
        </div>
        <div class="slide-visual">
          <div class="mock-panel">
            <!-- 账户余额汇总，独立区块，分割开 -->
            <!-- 账户资产：余额 / 累计消费 / 用户分组，复用 .mock-panel-row 行式（不沿用真实控制台 .stat-card） -->
            <div class="mock-panel-summary">
              <div class="mock-panel-row">
                <span class="dot dot-gold"></span>
                <span class="mock-balance">账户余额 ¥128.40</span>
                <span class="mock-panel-tag">按量计费</span>
              </div>
              <div class="mock-panel-row">
                <span class="dot dot-blue"></span>
                <span class="mock-balance">累计消费 ¥76.52</span>
                <span class="mock-panel-tag">消费开支</span>
              </div>
              <div class="mock-panel-row">
                <span class="dot dot-violet"></span>
                <span class="mock-balance">用户分组 vip</span>
                <span class="mock-panel-tag">会员权益</span>
              </div>
            </div>
            <!-- 密钥列表区域 -->
            <div class="mock-panel-list">
              <div class="mock-panel-row">
                <span class="dot dot-green" title="已启用"></span>
                <span class="mock-key"><span class="mock-key-label">密钥1：</span>sk‑agg‑72ce‑****‑3Fa9</span>
                <span class="mock-panel-tag">限额 ¥ 35</span>
              </div>
              <div class="mock-panel-row">
                <span class="dot dot-blue" title="已启用"></span>
                <span class="mock-key"><span class="mock-key-label">密钥2：</span>sk‑ehw‑b91f‑****‑82gh</span>
                <span class="mock-panel-tag">限额 ¥ 50</span>
              </div>
              <div class="mock-panel-row">
                <span class="dot dot-blue" title="已启用"></span>
                <span class="mock-key"><span class="mock-key-label">密钥3：</span>sk‑nvu‑24dd‑****‑71kc</span>
                <span class="mock-panel-tag">限额 ¥ 20</span>
              </div>
            </div>

          </div>
        </div>
      </div>
    </section>

    <!-- 屏6：开发文档 + CTA（深色收尾） -->
    <section class="slide slide-docs" :class="{ 'is-active': currentIndex === 5 }">
      <div class="slide-inner split">
        <div class="slide-copy slide-copy-light">
          <p class="slide-eyebrow eyebrow-cyan">05 · 开发文档</p>
          <h2 class="slide-title">三行代码，完成接入</h2>
          <p class="slide-desc">
            原生兼容 OpenAI SDK，仅替换 base_url 即可快速对接，控制台生成密钥，模型广场自由选择。
          </p>
          <div class="hero-actions">
            <a-button type="primary" @click="goToDocsPage">查看开发文档</a-button>
            <a-button ghost @click="handleStart">免费注册</a-button>
          </div>
        </div>
        <div class="slide-visual">
          <div class="mock-code">
            <div class="mock-code-head">
              <span class="dot dot-gold"></span> quickstart.py
            </div>
            <pre><span class="tok-kw">from</span> openai <span class="tok-kw">import</span> OpenAI

client = OpenAI(
    api_key=<span class="tok-str">"sk-agg-..."</span>,
    base_url=<span class="tok-str">"https://your-domain/v1"</span>,
)

resp = client.chat.completions.create(
    model=<span class="tok-str">"deepseek-v4-flash"</span>,
    messages=[{<span class="tok-str">"role"</span>: <span class="tok-str">"user"</span>, <span
                  class="tok-str">"content"</span>: <span class="tok-str">"你好"</span>}],
)</pre>
          </div>
        </div>
      </div>
      <footer class="slide-footer">
        AgenticAPI · 由 Agent 管理你的 API · OpenAI 兼容中转服务
      </footer>
    </section>

    <!-- 右侧圆点导航（桌面端） -->
    <nav class="slide-dots" aria-label="首页分屏导航">
      <button
          v-for="(s, i) in sections"
          :key="s.label"
          class="slide-dot"
          :class="{ 'slide-dot-active': currentIndex === i }"
          :title="s.label"
          @click="scrollToPage(i)"
      ><span class="slide-dot-label">{{ s.label }}</span></button>
    </nav>

    <!-- 左下角屏码 -->
    <div class="slide-counter">{{ String(currentIndex + 1).padStart(2, '0') }} /
      {{ String(sections.length).padStart(2, '0') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import {ref, computed, onMounted, onUnmounted} from 'vue'
import {useRouter} from 'vue-router'
import {useModelListStore} from '@/stores/modelList'
import {useUserStore} from '@/stores/user'
import LobeIcon from '@/components/common/LobeIcon.vue'
import LineChart from '@/components/monitor/LineChart.vue'
import logoMark from '@/assets/images/logo-mark.png'

const modelListStore = useModelListStore()
const userStore = useUserStore()
const router = useRouter()

// ── 路由跳转 ──
const goToModelsPage = () => router.push({name: 'Models'})
const goToStudioPage = () => router.push({name: 'Studio'})
const goToMonitorPage = () => router.push({name: 'Monitor'})
const goToDashboardPage = () => router.push({name: 'Dashboard'})
const goToDocsPage = () => router.push({name: 'Docs'})

// 已登录进控制台，未登录唤起注册弹窗
const handleStart = () => {
  if (userStore.isLoggedIn) {
    goToDashboardPage()
  } else {
    userStore.openAuthDialog('register')
  }
}

// ── 分屏定义（圆点导航 / 屏码共用） ──
const sections = [
  {label: '首页'},
  {label: '模型广场'},
  {label: '模型工坊'},
  {label: '监控面板'},
  {label: '控制台'},
  {label: '开发文档'},
]

// ── 模型广场展示卡：固定 8 张（4 行 2 列）；置顶模型优先，不足 8 个再从其余启用的模型补齐 ──
// 仅当站点完全没有任何模型（全新部署）时才退回演示数据占位
const demoModels = [
  {name: 'qwen-plus', icon: 'Qwen', group: 'free', inputPrice: '0.80', cachePrice: '0.00', outputPrice: '2.00'},
  {name: 'gpt-4o', icon: 'OpenAI', group: 'vip', inputPrice: '12.50', cachePrice: '0.00', outputPrice: '50.00'},
  {name: 'claude-sonnet', icon: 'Claude', group: 'vip', inputPrice: '21.00', cachePrice: '0.00', outputPrice: '105.00'},
  {name: 'deepseek-chat', icon: 'DeepSeek', group: 'free', inputPrice: '1.00', cachePrice: '0.00', outputPrice: '4.00'},
]

// ── 监控面板缩略版：调用次数折线图演示数据（复用监控页 LineChart 组件） ──
const monitorXData = ['08-13', '08-14', '08-15', '08-16', '08-17', '08-18', '08-19', '08-20', '08-21']
const monitorSeries = [
  {
    name: 'step-3.7-flash',
    data: [214, 287, 302, 268, 341, 389, 356, 412, 487]
  },
  {
    name: 'glm-5.3',
    data: [97, 108, 115, 189, 234, 261, 198, 172, 163]
  },
  {
    name: 'other',
    data: [28, 41, 33, 37, 29, 45, 38, 31, 43]
  }
]

const showcaseModels = computed(() => {
  const all = modelListStore.totalModelList.filter(m => m.status)
  // 全新站点（无任何模型）才用演示数据占位，避免真实数据与演示卡片混排
  if (all.length === 0) return demoModels
  // 置顶优先，其余按列表顺序补齐
  const ordered = [...all.filter(m => m.isPin), ...all.filter(m => !m.isPin)]
  return ordered
      .slice(0, 8)
      .map(m => ({
        name: m.name,
        icon: m.icon || m.name,
        group: m.modelGroup,
        inputPrice: String(parseFloat(String(m.inputPrice)) || 0),
        cachePrice: String(parseFloat(String(m.cachePrice)) || 0),
        outputPrice: String(parseFloat(String(m.outputPrice)) || 0),
      }))
})


// ═══════════ 整页滑动控制（滚轮 / 触摸 / 键盘 / 圆点） ═══════════
const containerRef = ref<HTMLDivElement | null>(null)
const currentIndex = ref(0)
const isScrolling = ref(false)
// 窄屏（手机）退化为普通纵向滚动，不做滚轮劫持
const desktopQuery = window.matchMedia('(min-width: 769px)')

function scrollToPage(index: number) {
  if (index < 0 || index >= sections.length) return
  if (isScrolling.value) return

  currentIndex.value = index
  const container = containerRef.value
  if (!container) return

  if (desktopQuery.matches) {
    isScrolling.value = true
    container.scrollTo({top: index * container.clientHeight, behavior: 'smooth'})
    setTimeout(() => {
      isScrolling.value = false
    }, 700)
  } else {
    container.scrollTo({top: index * container.clientHeight, behavior: 'smooth'})
  }
}

const handleWheel = (e: WheelEvent) => {
  if (!desktopQuery.matches) return
  e.preventDefault()
  if (isScrolling.value) return
  if (e.deltaY > 10) scrollToPage(currentIndex.value + 1)
  else if (e.deltaY < -10) scrollToPage(currentIndex.value - 1)
}

let touchStartY = 0
const handleTouchStart = (e: TouchEvent) => {
  const touch = e.touches[0]
  if (touch) touchStartY = touch.clientY
}
const handleTouchMove = (e: TouchEvent) => {
  if (isScrolling.value) return
  const touch = e.touches[0]
  if (!touch) return
  const diff = touch.clientY - touchStartY
  if (diff < -40) scrollToPage(currentIndex.value + 1)
  else if (diff > 40) scrollToPage(currentIndex.value - 1)
}

const handleKeydown = (e: KeyboardEvent) => {
  // 焦点在输入框 / 弹窗内（如登录弹窗）时不翻页
  const target = e.target as HTMLElement | null
  if (target?.closest?.('input, textarea, .arco-modal, .arco-drawer')) return
  if (e.key === 'ArrowDown' || e.key === 'PageDown') scrollToPage(currentIndex.value + 1)
  else if (e.key === 'ArrowUp' || e.key === 'PageUp') scrollToPage(currentIndex.value - 1)
}

onMounted(() => {
  const dom = containerRef.value
  if (!dom) return
  // passive:false 才能调用 e.preventDefault()（滚轮劫持仅在桌面生效）
  dom.addEventListener('wheel', handleWheel, {passive: false})
  dom.addEventListener('touchstart', handleTouchStart, {passive: true})
  dom.addEventListener('touchmove', handleTouchMove, {passive: true})
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  const dom = containerRef.value
  if (!dom) return
  dom.removeEventListener('wheel', handleWheel)
  dom.removeEventListener('touchstart', handleTouchStart)
  dom.removeEventListener('touchmove', handleTouchMove)
  window.removeEventListener('keydown', handleKeydown)
})

// ═══════════ 首屏动态标识：鼠标视差（摘取自参考 HTML，reduced-motion 时静止） ═══════════
const heroSectionRef = ref<HTMLElement | null>(null)
let markFrameId = 0
let markTx = 0, markTy = 0, markPx = 0, markPy = 0
let markReduce = false

function handleMarkPointer(e: PointerEvent) {
  const el = heroSectionRef.value
  if (!el) return
  const r = el.getBoundingClientRect()
  markTx = (e.clientX - r.left) / r.width - 0.5
  markTy = (e.clientY - r.top) / r.height - 0.5
}

function resetMarkPointer() {
  markTx = 0
  markTy = 0
}

function markFrame() {
  markPx += (markTx - markPx) * 0.055
  markPy += (markTy - markPy) * 0.055
  const el = heroSectionRef.value
  if (el) {
    el.style.setProperty('--px', (markReduce ? 0 : markPx).toFixed(4))
    el.style.setProperty('--py', (markReduce ? 0 : markPy).toFixed(4))
  }
  markFrameId = requestAnimationFrame(markFrame)
}

onMounted(() => {
  markReduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const el = heroSectionRef.value
  if (el) {
    el.addEventListener('pointermove', handleMarkPointer, {passive: true})
    el.addEventListener('pointerleave', resetMarkPointer)
  }
  markFrameId = requestAnimationFrame(markFrame)
})

onUnmounted(() => {
  cancelAnimationFrame(markFrameId)
  const el = heroSectionRef.value
  if (el) {
    el.removeEventListener('pointermove', handleMarkPointer)
    el.removeEventListener('pointerleave', resetMarkPointer)
  }
})
</script>

<style scoped>
.home-page {
  position: relative;
  height: 100%;
  overflow: hidden;
  background-color: var(--color-bg);
  /* 首页保留改版前的字体与排版：控制台页的字体/样式改版不作用于这里 */
  --font-sans: 'Public Sans Variable', 'Public Sans', 'HarmonyOS Sans SC', 'MiSans', 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, 'Segoe UI', Arial, sans-serif;
  --font-display: 'Playfair Display Variable', 'Playfair Display', 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'SimSun', serif;
  font-family: var(--font-sans);
  letter-spacing: normal;
  font-variant-numeric: normal;
}

/* 首页共享类与 Arco 组件保留改版前观感 */
.home-page .stat-card {
  box-shadow: none;
}

.home-page .stat-label {
  color: var(--color-text-muted);
  letter-spacing: normal;
}

.home-page .stat-value {
  font-size: 20px;
  font-weight: var(--font-semibold);
  letter-spacing: normal;
}

.home-page :deep(.arco-btn) {
  font-weight: var(--font-normal);
  letter-spacing: normal;
  box-shadow: none;
}

/* ═══════════ 分屏骨架 ═══════════ */
.slide {
  position: relative;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.slide-inner {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1080px;
  padding: var(--space-6) var(--space-6);
  /* 入场动效：仅当前屏内容完全显形，其余屏降低存在感 */
  opacity: 0.3;
  transform: translateY(14px);
  transition: opacity 0.5s ease, transform 0.5s ease;
}

.slide.is-active .slide-inner {
  opacity: 1;
  transform: translateY(0);
}

/* 眉题：等宽字体 + 宽字距，工程产品风格 */
.slide-eyebrow {
  margin: 0 0 var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  letter-spacing: 0.18em;
  color: var(--color-text-muted);
}

.eyebrow-blue {
  color: var(--color-primary);
}

.eyebrow-violet {
  color: var(--color-violet);
}

.eyebrow-green {
  color: var(--color-success);
}

.eyebrow-orange {
  color: var(--color-accent);
}

.eyebrow-cyan {
  color: var(--color-cyan);
}

.slide-title {
  margin: 0 0 var(--space-3);
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  font-weight: var(--font-semibold);
  /* 衬线中文标题：留出呼吸感，字距微放、行高放宽 */
  letter-spacing: 0.035em;
  color: var(--color-text);
  line-height: 1.45;
}

.slide-desc {
  margin: 0 0 var(--space-5);
  font-size: var(--text-base);
  line-height: var(--leading-relaxed);
  color: var(--color-text-secondary);
  max-width: 30em;
}

/* ═══════════ 屏1：Hero ═══════════ */
.slide-hero {
  background-color: var(--color-bg);
}

/* 点阵网格：工程图纸质感，径向遮罩向边缘淡出（蓝调融入光效） */
.slide-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  background-image: radial-gradient(circle, rgba(22, 93, 255, 0.3) 1px, transparent 1px);
  background-size: 22px 22px;
  mask-image: radial-gradient(ellipse 65% 55% at 50% 38%, black 20%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse 65% 55% at 50% 38%, black 20%, transparent 75%);
  opacity: 0.4;
  pointer-events: none;
}

/* 静态渐变背景（借鉴 Nexus）：顶部色带光束铺底，三枚大尺度模糊色斑固定构图，
   颜色取站点强调色（arcoblue / 紫 / 青），亮色主题下低透明度不喧宾夺主。
   不做漂移动画——大面积 blur 的持续重绘开销大，静态渐变保证流畅 */
.hero-aurora {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
  /* 提升为独立合成层：翻页滚动时整层纹理平移，避免反复光栅化 */
  transform: translateZ(0);
}

.hero-aurora::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse 75% 55% at 50% 0%, rgba(22, 93, 255, 0.14) 0%, transparent 62%),
  radial-gradient(ellipse 42% 42% at 88% 26%, rgba(114, 46, 209, 0.10) 0%, transparent 70%),
  radial-gradient(ellipse 38% 38% at 8% 72%, rgba(20, 201, 201, 0.08) 0%, transparent 70%);
}

.aurora-blob {
  position: absolute;
  width: 52vmax;
  height: 52vmax;
  border-radius: 50%;
  /* 不用 filter: blur —— 大尺度模糊的光栅化开销是翻页卡顿的主因，
     改用多段径向渐变止点模拟同样的柔和扩散，视觉等效且零滤镜成本 */
}

.blob-blue {
  top: -16%;
  left: 8%;
  background: radial-gradient(circle,
  rgba(22, 93, 255, 0.32) 0%,
  rgba(22, 93, 255, 0.16) 30%,
  rgba(22, 93, 255, 0.06) 55%,
  transparent 72%);
}

.blob-violet {
  top: -10%;
  right: -6%;
  background: radial-gradient(circle,
  rgba(114, 46, 209, 0.26) 0%,
  rgba(114, 46, 209, 0.13) 30%,
  rgba(114, 46, 209, 0.05) 55%,
  transparent 72%);
}

.blob-cyan {
  bottom: -24%;
  left: 32%;
  background: radial-gradient(circle,
  rgba(20, 201, 201, 0.22) 0%,
  rgba(20, 201, 201, 0.11) 30%,
  rgba(20, 201, 201, 0.04) 55%,
  transparent 72%);
}

.hero-inner {
  text-align: center;
}

.hero-title {
  margin: 0 0 var(--space-4);
  font-family: var(--font-display);
  font-size: clamp(36px, 4.6vw, 52px);
  font-weight: var(--font-bold);
  /* 衬线中文大标题：正字距 + 宽行高，避免拥挤 */
  letter-spacing: 0.05em;
  line-height: 1.5;
  color: var(--color-text);
}

/* 关键词：品牌三色静态渐变文字（借鉴 Nexus 渐变标题） */
.hero-title-key {
  background: linear-gradient(100deg, #165dff 0%, #722ed1 45%, #14c9c9 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.hero-desc {
  margin: 0 0 var(--space-6);
  font-size: var(--text-base);
  color: var(--color-text-secondary);
}

.hero-actions {
  display: flex;
  justify-content: center;
  gap: var(--space-3);
  margin-bottom: var(--space-8);
}

/* 主按钮：品牌色外发光（借鉴 Nexus CTA） */
.hero-actions :deep(.arco-btn-primary) {
  box-shadow: 0 6px 22px rgba(22, 93, 255, 0.35);
}

/* 数据速览：半透明面板浮于光效之上，等宽数字。
   不用 backdrop-filter —— 滚动时它每帧重滤背后内容，开销大；
   提高底色不透明度在淡色静态背景上观感几乎一致 */
.hero-metrics {
  position: relative;
  display: inline-flex;
  align-items: stretch;
  gap: var(--space-8);
  padding: var(--space-4) var(--space-8);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(22, 93, 255, 0.14);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-md);
}

.hero-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 72px;
}

.hero-metric + .hero-metric {
  border-left: 1px solid var(--color-border);
  padding-left: var(--space-8);
}

.hero-metric-value {
  font-family: var(--font-mono);
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.hero-metric-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* 向下滚动提示 */
.scroll-hint {
  position: absolute;
  left: 50%;
  bottom: 18px;
  z-index: 2;
  transform: translateX(-50%);
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  color: var(--color-text-muted);
  background-color: var(--color-white);
  cursor: pointer;
  animation: hint-float 2s ease-in-out infinite;
}

@keyframes hint-float {
  0%, 100% {
    transform: translate(-50%, 0);
  }
  50% {
    transform: translate(-50%, 5px);
  }
}

/* ═══════════ 通用左右分栏屏 ═══════════ */
.split {
  display: grid;
  grid-template-columns: 5fr 6fr;
  align-items: center;
  gap: var(--space-10);
}

.split-reverse {
  grid-template-columns: 6fr 5fr;
}

.split-reverse .slide-copy {
  order: 2; /* 文字放到第二列（右侧，5fr） */
}

.split-reverse .slide-visual {
  order: 1; /* 组件放到第一列（左侧，6fr） */
}

/* 各分屏底色：本屏强调色的极浅色调打底，再叠一层偏向视觉区的径向光晕
   （借鉴 Nexus 的 section halo），光晕位置跟随左右分栏的视觉面板一侧 */
.slide-models {
  background: radial-gradient(ellipse 55% 62% at 74% 45%, rgba(22, 93, 255, 0.1) 0%, transparent 65%),
  linear-gradient(160deg, var(--color-primary-lighter) 0%, var(--color-bg) 55%);
}

.slide-studio {
  background: radial-gradient(ellipse 55% 62% at 26% 45%, rgba(114, 46, 209, 0.09) 0%, transparent 65%),
  linear-gradient(200deg, var(--color-violet-lighter) 0%, var(--color-bg) 55%);
}

.slide-monitor {
  background: radial-gradient(ellipse 55% 62% at 74% 45%, rgba(0, 180, 42, 0.09) 0%, transparent 65%),
  linear-gradient(160deg, var(--color-success-light) 0%, var(--color-bg) 55%);
}

.slide-console {
  background: radial-gradient(ellipse 55% 62% at 26% 45%, rgba(255, 125, 0, 0.1) 0%, transparent 65%),
  linear-gradient(200deg, var(--color-warning-light) 0%, var(--color-bg) 55%);
}

/* ═══════════ 产品 UI 模拟 ═══════════ */

/* 通用：悬浮上浮 + 阴影抬升，顶部一条强调色高光线（--glow-color 按屏指定） */
.mock-model-card,
.mock-chat,
.mock-stat,
.mock-chart,
.mock-panel,
.mock-code {
  position: relative;
  transition: transform var(--transition-slow), box-shadow var(--transition-slow);
}

.mock-model-card:hover,
.mock-chat:hover,
.mock-chart:hover,
.mock-panel:hover,
.mock-code:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}

.mock-stat:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.mock-chat::after,
.mock-chart::after,
.mock-panel::after,
.mock-code::after {
  content: '';
  position: absolute;
  top: 0;
  left: 15%;
  width: 70%;
  height: 2px;
  border-radius: 1px;
  background: linear-gradient(90deg, transparent, var(--glow-color, var(--color-primary)), transparent);
  opacity: 0.55;
}


/* 思维链折叠块（对齐工坊 .reasoning-block：橙色警示调，与正文分层） */
.mock-reasoning {
  margin-bottom: var(--space-2);
  border: 1px solid rgba(255, 125, 0, 0.25);
  border-radius: var(--radius-md);
  background: var(--color-warning-light);
  overflow: hidden;
}

.mock-reasoning-header {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 4px 8px;
  font-size: var(--text-xs);
  color: var(--color-accent-dark);
}

/* 展开态：箭头旋转 90° 朝下（静态展示，不做点击折叠交互） */
.mock-reasoning-arrow {
  font-size: 12px;
  transform: rotate(90deg);
}

.mock-reasoning-text {
  padding: 6px 10px 8px;
  font-size: var(--text-xs);
  line-height: 1.7;
  color: var(--color-text-secondary);
  border-top: 1px solid rgba(255, 125, 0, 0.2);
}

/* 助手正文（包一层 div，便于和思维链分块堆叠） */
.mock-chat-text {
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--color-text);
}

.mock-chat-text code {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--color-gray-200);
  padding: 1px 5px;
  border-radius: var(--radius-sm);
}

.mock-chat {
  --glow-color: var(--color-violet);
}

.mock-chart {
  --glow-color: var(--color-success);
}

.mock-panel {
  --glow-color: var(--color-accent);
}

.mock-code {
  --glow-color: var(--color-cyan);
}

/* 屏2：模型卡片 */
.mock-card-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
}

.mock-model-card {
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3) var(--space-4);
  box-shadow: var(--shadow-sm);
}

.mock-model-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.mock-model-name {
  flex: 1;
  min-width: 0;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mock-model-tag {
  font-size: var(--text-xs);
  line-height: 18px;
  padding: 0 6px;
  border-radius: var(--radius-sm);
}

.tag-free {
  color: var(--color-success);
  background-color: var(--color-success-light);
}

.tag-vip {
  color: var(--color-vermilion);
  background-color: var(--color-vermilion-lighter);
}

.mock-model-price {
  display: flex;
  gap: var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.mock-model-price b {
  font-family: var(--font-mono);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

/* 屏3：对话面板 */
.mock-chat {
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.mock-chat-row {
  max-width: 86%;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  border-radius: var(--radius-lg);
}

.mock-chat-user {
  align-self: flex-end;
  background-color: var(--color-primary);
  color: var(--color-on-primary);
  border-bottom-right-radius: var(--radius-sm);
}

.mock-chat-ai {
  align-self: flex-start;
  background-color: var(--color-gray-50);
  border: 1px solid var(--color-border);
  border-bottom-left-radius: var(--radius-sm);
  color: var(--color-text);
}

/* 流式输出光标 */
.mock-caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.15em;
  background-color: var(--color-violet);
  animation: caret-blink 0.9s steps(1) infinite;
}

@keyframes caret-blink {
  50% {
    opacity: 0;
  }
}

.mock-chat-meta {
  display: flex;
  gap: var(--space-4);
  padding-top: var(--space-2);
  border-top: 1px dashed var(--color-border);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* ═══════════ 屏4：监控面板缩略版（4 卡片 2×2 + 调用次数折线图） ═══════════ */
/* 单卡样式复用全局 .stat-card（左色脊 + 等宽数值），此处只定 2×2 网格并收紧尺寸 */
.mock-stat-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

/* 缩略面板里卡片收紧一点，数值字号从 20px 降到 16px 更协调（可选） */
.mock-stat-grid .stat-card {
  padding: var(--space-2) var(--space-3);
}

.mock-stat-grid .stat-value {
  font-size: var(--text-base);
}

/* 折线图卡片：复用监控页 .chart-cell 的白底卡片质感 */
.mock-chart-card {
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
}

.mock-chart-title {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  margin-bottom: var(--space-2);
  color: var(--color-text);
}

/* 屏5：控制台列表 */
.mock-panel {
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.mock-panel-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
}

.mock-panel-row + .mock-panel-row {
  border-top: 1px solid var(--color-border);
}

.mock-key {
  flex: 1;
  font-family: var(--font-mono);
  color: var(--color-text);
}

/* 密钥行的"密钥N："标签用正文体（与"账户余额"一致），密钥串仍走等宽 */
.mock-key-label {
  font-family: var(--font-sans);
}

/* 资产区与密钥区之间加一道分割线（两段都是 .mock-panel-row，用边框区分区块） */
.mock-panel-list {
  border-top: 1px solid var(--color-border);
}

.mock-balance {
  flex: 1;
  color: var(--color-text);
}

.mock-panel-tag {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  background-color: var(--color-gray-50);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 0 6px;
  line-height: 18px;
}

/* 状态点 */
.dot {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.dot-green {
  background-color: var(--color-success);
}

.dot-blue {
  background-color: var(--color-primary);
}

.dot-violet {
  background-color: var(--color-violet);
}

.dot-gold {
  background-color: var(--color-gold);
}

/* 屏6：深色收尾 */
.slide-docs {
  background-color: var(--color-gray-900);
}

/* 深色屏光晕：蓝紫双色呼应 Hero 的 aurora */
.slide-docs::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  background: radial-gradient(ellipse 55% 55% at 72% 42%, rgba(22, 93, 255, 0.16) 0%, transparent 62%),
  radial-gradient(ellipse 40% 45% at 18% 68%, rgba(114, 46, 209, 0.13) 0%, transparent 65%);
  pointer-events: none;
}

.slide-docs .slide-title,
.slide-docs .slide-copy-light {
  color: var(--color-white);
}

.slide-docs .slide-desc {
  color: var(--color-gray-400);
}

.slide-docs .hero-actions {
  justify-content: flex-start;
  margin-bottom: 0;
}

.mock-code {
  background-color: var(--color-gray-800);
  border: 1px solid var(--color-gray-700, #4e5969);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}

.mock-code-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--color-gray-700, #4e5969);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-gray-400);
}

.mock-code pre {
  margin: 0;
  padding: var(--space-4);
  font-family: var(--font-mono);
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--color-gray-100);
  overflow-x: auto;
}

.tok-kw {
  color: #c384f5;
}

.tok-str {
  color: #7ce38b;
}

.slide-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: var(--space-3) var(--space-6);
  border-top: 1px solid var(--color-gray-700, #4e5969);
  font-size: var(--text-xs);
  color: var(--color-gray-300);
  text-align: center;
}

/* ═══════════ 导航：右侧圆点 + 左下屏码 ═══════════ */
.slide-dots {
  position: fixed;
  right: 18px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 10;
}

.slide-dot {
  position: relative;
  width: 8px;
  height: 8px;
  padding: 0;
  border: none;
  border-radius: var(--radius-full);
  background-color: var(--color-gray-300);
  cursor: pointer;
  transition: background-color var(--transition-fast), transform var(--transition-fast);
}

.slide-dot:hover {
  background-color: var(--color-gray-500);
}

.slide-dot-active {
  background-color: var(--color-primary);
  transform: scale(1.25);
}

/* 悬停显示分屏名称 */
.slide-dot-label {
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  white-space: nowrap;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--transition-fast);
}

.slide-dot:hover .slide-dot-label {
  opacity: 1;
}

.slide-counter {
  position: fixed;
  left: 20px;
  bottom: 16px;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  letter-spacing: 0.08em;
  z-index: 10;
}

/* ═══════════ 响应式：窄屏退化为普通滚动 ═══════════ */
@media (prefers-reduced-motion: reduce) {
  .scroll-hint,
  .mock-caret {
    animation: none;
  }
}

@media (max-width: 768px) {
  .home-page {
    overflow-y: auto;
  }

  .slide {
    min-height: 100%;
    padding: var(--space-8) 0;
  }

  .slide-inner {
    opacity: 1;
    transform: none;
  }

  .hero-title {
    font-size: var(--text-3xl);
  }

  .hero-metrics {
    flex-wrap: wrap;
    gap: var(--space-4);
    padding: 0;
  }

  .hero-metric + .hero-metric {
    border-left: none;
    padding-left: 0;
  }

  .split,
  .split-reverse {
    grid-template-columns: 1fr;
    gap: var(--space-6);
  }

  /* 单列时恢复源顺序：文字在前，组件在后 */
  .split-reverse .slide-copy,
  .split-reverse .slide-visual {
    order: 0;
  }

  .slide-dots,
  .slide-counter,
  .scroll-hint {
    display: none;
  }
}

/* ═══════════ 首屏动态标识（摘取自 docs/assets/参考的首页组件.html） ═══════════ */
.hero-mark {
  width: min(100%, 760px);
  margin: 0 auto var(--space-5);
  pointer-events: none;
}

.mark-flow-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 1240 / 440;
  max-height: clamp(150px, 23vh, 240px);
}

.mark-flow {
  display: block;
  width: 100%;
  height: 100%;
  transform: translate3d(calc(var(--px, 0) * 16px), calc(var(--py, 0) * 12px), 0);
  transition: transform .14s linear;
}

.mark-lanes { transform-box: fill-box; transform-origin: center; }

.rb-bed-halo {
  fill: none; stroke: url(#markPulseGrad); stroke-width: 30;
  stroke-linecap: round; opacity: .16; filter: blur(9px);
}
.rb-bed {
  fill: none; stroke: url(#markFlowGrad); stroke-width: 3.2;
  stroke-linecap: round; opacity: .26;
}
.rb-pulse {
  fill: none; stroke-linecap: butt;
  animation: markStream 3s linear infinite;
  animation-delay: var(--phase, 0s);
  will-change: stroke-dashoffset;
}
.rb-halo {
  stroke: url(#markPulseGrad); stroke-width: 26; stroke-linecap: round;
  opacity: .5; filter: blur(6px); stroke-dasharray: 180 220;
}
.rb-beam {
  stroke: url(#markFlowGrad); stroke-width: 11;
  opacity: .6; filter: blur(1px); stroke-dasharray: 0.01 96 84 219.99;
}
.rb-head {
  stroke: url(#markPulseGrad); stroke-width: 8;
  opacity: .98; stroke-dasharray: 0.01 152 28 219.99;
}
@keyframes markStream {
  0%   { stroke-dashoffset: 0; }
  5%   { stroke-dashoffset: -12.58; }
  10%  { stroke-dashoffset: -25.89; }
  15%  { stroke-dashoffset: -40.58; }
  20%  { stroke-dashoffset: -57.17; }
  25%  { stroke-dashoffset: -76; }
  30%  { stroke-dashoffset: -97.17; }
  35%  { stroke-dashoffset: -120.58; }
  40%  { stroke-dashoffset: -145.89; }
  45%  { stroke-dashoffset: -172.58; }
  50%  { stroke-dashoffset: -200; }
  55%  { stroke-dashoffset: -227.42; }
  60%  { stroke-dashoffset: -254.11; }
  65%  { stroke-dashoffset: -279.42; }
  70%  { stroke-dashoffset: -302.83; }
  75%  { stroke-dashoffset: -324; }
  80%  { stroke-dashoffset: -342.83; }
  85%  { stroke-dashoffset: -359.42; }
  90%  { stroke-dashoffset: -374.11; }
  95%  { stroke-dashoffset: -387.42; }
  100% { stroke-dashoffset: -400; }
}

/* 中央玻璃节点：内嵌 logo1 定稿主标，替代参考稿里的远程图片 */
.mark-node-parallax {
  position: absolute;
  left: 50%; top: 50%;
  transform: translate(-50%, -50%)
             translate3d(calc(var(--px, 0) * -24px), calc(var(--py, 0) * -18px), 0)
             rotateY(calc(var(--px, 0) * 5deg)) rotateX(calc(var(--py, 0) * -5deg));
  transform-style: preserve-3d;
  transition: transform .16s ease-out;
}
.mark-node {
  width: clamp(96px, 12vw, 148px);
  height: clamp(96px, 12vw, 148px);
  border-radius: clamp(22px, 2.6vw, 34px);
  display: flex; align-items: center; justify-content: center;
  background: rgba(255, 255, 255, .6);
  border: 1px solid rgba(255, 255, 255, .92);
  backdrop-filter: blur(18px) saturate(125%);
  -webkit-backdrop-filter: blur(18px) saturate(125%);
  box-shadow: 0 30px 60px -26px rgba(28, 43, 69, .28), inset 0 1px 0 rgba(255, 255, 255, .95);
  overflow: hidden;
  animation: markNodeTick 3s linear infinite;
  animation-delay: -1s;
}
.mark-node-logo {
  position: relative; z-index: 1;
  width: 82%; height: 82%; object-fit: contain;
}
.mark-sheen {
  position: absolute; inset: -32%; border-radius: 50%; pointer-events: none;
  background: radial-gradient(34% 34% at 30% 26%, rgba(255, 255, 255, .92), rgba(255, 255, 255, 0) 72%);
  animation: markSheen 12s linear infinite;
}
@keyframes markSheen { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes markNodeTick {
  0%, 2%, 98%, 100% { transform: scale(1) translateY(0); }
  9%  { transform: scale(1.012) translateY(-1px); }
  16%, 35% { transform: scale(1) translateY(0); }
  42% { transform: scale(1.012) translateY(-1px); }
  49%, 68% { transform: scale(1) translateY(0); }
  75% { transform: scale(1.012) translateY(-1px); }
  82% { transform: scale(1) translateY(0); }
}

.mark-labels {
  display: flex; justify-content: space-between;
  width: min(100%, 640px);
  margin: -4px auto 0;
  font-family: var(--font-mono);
  font-size: 10px; font-weight: 500; letter-spacing: .34em;
  color: var(--color-text-muted); opacity: .72;
}
.mark-labels span::before {
  content: ''; display: inline-block; width: 14px; height: 1px;
  margin-right: 9px; vertical-align: middle;
  background: linear-gradient(90deg, #7FA9EC, #A9A4E9);
}

@media (max-width: 768px) {
  .hero-mark { margin-bottom: var(--space-3); }
  .mark-labels { display: none; }
  .rb-halo { stroke-width: 18; }
  .rb-beam { stroke-width: 8; }
  .rb-head { stroke-width: 6; }
}
@media (prefers-reduced-motion: reduce) {
  .rb-pulse, .mark-sheen, .mark-node, .mark-node-parallax, .mark-flow {
    animation: none !important;
    transition: none !important;
  }
  .rb-halo, .rb-beam, .rb-head { stroke-dashoffset: -208; }
}
</style>
