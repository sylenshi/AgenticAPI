<!-- 文档 -->

<template>
  <div class="docs-page">
    <!-- 左侧目录 -->
    <aside class="docs-sidebar">
      <div class="sidebar-header">
        <h2 class="sidebar-title">文档</h2>
      </div>
      <nav class="sidebar-nav">
        <div v-for="group in docGroups" :key="group.title" class="nav-group">
          <div class="nav-group-title">{{ group.title }}</div>
          <ul>
            <li v-for="doc in group.docs" :key="doc.path">
              <a
                  :class="{ active: activePath === doc.path }"
                  @click="loadDoc(doc.path)"
              >
          <span class="nav-icon">
            <!-- 保持原来的两段 svg 不变 -->
          </span>
                <span class="nav-text">{{ doc.title }}</span>
              </a>
            </li>
          </ul>
        </div>
      </nav>
    </aside>

    <!-- 中间内容 -->
    <main class="docs-content">
      <div class="content-wrapper">
        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          <p class="loading-text">加载中...</p>
        </div>
        <div v-else-if="!renderedContent" class="empty-state">
          <svg class="empty-icon" xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          <h3 class="empty-title">选择一篇文档开始阅读</h3>
          <p class="empty-description">从左侧目录中选择一篇文档查看内容</p>
        </div>
        <div v-else class="prose" v-html="renderedContent"></div>
      </div>
    </main>

    <!-- 右侧目录 -->
    <aside class="docs-toc">
      <div class="toc-header">
        <span class="toc-title">目录</span>
      </div>
      <nav class="toc-nav">
        <ul v-if="tocList.length">
          <li v-for="item in tocList" :key="item.id"
              :class="['toc-level-' + item.level, { active: activeHeading === item.id }]">
            <a @click="scrollToHeading(item.id)">{{ item.text }}</a>
          </li>
        </ul>
        <p v-else class="toc-empty">本文档无目录</p>
      </nav>
    </aside>
  </div>
</template>


<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import {ref, onMounted, onBeforeUnmount, nextTick} from 'vue'

const md = new MarkdownIt()

// 给 markdown 表格包一层可横向滚动的容器：窄屏宽表格只在自己内部滚动，
// 不把整个内容列撑出横向滚动条；桌面宽度下容器不做任何视觉改动。
md.renderer.rules.table_open = (tokens, idx, options, _env, self) =>
    '<div class="table-scroll">' + self.renderToken(tokens, idx, options)
md.renderer.rules.table_close = (tokens, idx, options, _env, self) =>
    self.renderToken(tokens, idx, options) + '</div>'

const renderedContent = ref('')
const activePath = ref('')
const loading = ref(false)

const docGroups = [
  {
    title: '用户文档',
    docs: [
      {title: 'API 调用文档', path: '/docs/API调用文档.md'},
    ],
  },
  {
    title: '开发者文档',
    docs: [
      {title: '后端接口规范', path: '/docs/后端API接口规范.md'},
      {title: '数据库设计', path: '/docs/数据库设计文档.md'},
      {title: '维护 Agent 设计', path: '/docs/维护Agent设计文档.md'},
      {title: '前端样式规范', path: '/docs/前端UI构建规范.md'},
    ],
  },
]

// loadDoc 去掉 index 参数
async function loadDoc(path: string) {
  loading.value = true
  activePath.value = path
  try {
    const res = await fetch(path)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const text = await res.text()
    if (text.trimStart().startsWith('<!DOCTYPE')) {
      throw new Error('文档不存在或路径错误')
    }
    renderedContent.value = md.render(text)
    loading.value = false          // 先关 loading，.prose 才会进入 DOM
    await nextTick()               // 等 DOM 更新完再去查标题
    buildToc()
    setupScrollSpy()              // 滚动高亮：观察标题进入视口
  } catch (error) {
    renderedContent.value =
        `<p style="color:var(--color-error)">文档加载失败：${path}<br/>${(error as Error).message}</p>`
    tocList.value = []
    activeHeading.value = ''
    tocObserver?.disconnect()
    console.error('加载文档失败:', error)
  } finally {
    loading.value = false
  }

}

// ── 右侧目录（TOC） ──
const tocList = ref<{ level: number; text: string; id: string }[]>([])

/** 渲染完成后扫描 .prose 里的标题，生成目录并给每个标题打上锚点 id */
function buildToc() {
  const container = document.querySelector('.prose')
  if (!container) {
    tocList.value = [];
    return
  }
  const headings = Array.from(container.querySelectorAll('h1, h2, h3'))
  tocList.value = headings.map((el, i) => {
    const id = `heading-${i}`
    el.id = id
    return {
      level: Number(el.tagName.slice(1)),
      text: (el.textContent || '').trim(),
      id,
    }
  })
}

/** 点击目录项 -> 平滑滚动到对应标题 */
function scrollToHeading(id: string) {
  document.getElementById(id)?.scrollIntoView({behavior: 'smooth', block: 'start'})
}

// ── 滚动高亮：当前可视区最靠上的标题即激活项 ──
const activeHeading = ref('')
let tocObserver: IntersectionObserver | null = null

function setupScrollSpy() {
  tocObserver?.disconnect()
  const root = document.querySelector('.docs-content') as HTMLElement | null
  if (!root || !tocList.value.length) return
  // rootMargin 下边收 70%：仅当标题落在视口上 30% 区间才算"当前章节"
  tocObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries
            .filter((e) => e.isIntersecting)
            .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) activeHeading.value = (visible[0].target as HTMLElement).id
      },
      {root, rootMargin: '0px 0px -70% 0px', threshold: 0},
  )
  tocList.value.forEach((item) => {
    const el = document.getElementById(item.id)
    if (el && tocObserver) tocObserver.observe(el)
  })
}

onBeforeUnmount(() => {
  tocObserver?.disconnect()
  tocObserver = null
})

onMounted(() => {
  const first = docGroups[0]?.docs[0]
  if (first) loadDoc(first.path)
})
</script>

<style scoped>
.docs-page {
  /* 正文留白与代码块出血共用同一个变量，避免不同断点下二者对不齐 */
  --docs-gutter: clamp(24px, 4vw, 56px);

  display: grid;
  /* 左右定宽、中间弹性；minmax(0, 1fr) 防止长代码 / 宽表格把中间列撑开 */
  grid-template-columns: 200px minmax(0, 1fr) 220px;
  /* 外层 .app-main 是 calc(100vh - 56px) 且 overflow:hidden，
     这里再用 100vh 会高出一条 header、底部被裁掉，故改为 100% */
  height: 100%;
  min-height: 0;
  background-color: var(--color-bg);
}

/* ═══════════════════════════════════════════════════════════
   左侧目录
   ═══════════════════════════════════════════════════════════ */

.docs-sidebar {
  /* --------------------↓侧边栏宽度↓-------------------- */
  width: 200px;
  /* --------------------↑侧边栏宽度↑-------------------- */
  background-color: var(--color-white);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: var(--space-6);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin: 0;
}

.sidebar-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
}

.sidebar-nav {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) 0;
}

.sidebar-nav ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.sidebar-nav li {
  margin: 0;
}

.sidebar-nav a {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: 2px var(--space-3);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  font-weight: var(--font-normal);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  border-radius: var(--radius-md);
  border-left: none;
}

.sidebar-nav a:hover {
  background-color: var(--color-gray-100);
  color: var(--color-text);
}

.sidebar-nav a.active {
  background-color: var(--color-primary-lighter);
  color: var(--color-primary);
  font-weight: var(--font-medium);
  box-shadow: none;
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: inherit;
}

.nav-text {
  flex: 1;
}

/* ═══════════════════════════════════════════════════════════
   右侧内容区
   ═══════════════════════════════════════════════════════════ */

.docs-content {
  min-width: 0;
  min-height: 0;
  background-color: var(--color-white);
  overflow-y: auto;
}

.content-wrapper {
  width: 100%;
  /* 原来 max-width 取 --container-lg（1024px），在 1385px 视口下比中间列还宽，
     margin:0 auto 计算为 0，居中完全没生效。
     换成更高的阅读上限 + 真正居中：窄屏铺满中间列，超宽屏行长也不失控 */
  max-width: 1180px;
  margin: 0 auto;
  padding: var(--space-10) var(--docs-gutter);
}

/* ═══════════════════════════════════════════════════════════
   加载状态
   ═══════════════════════════════════════════════════════════ */

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-20) 0;
}

.loading-text {
  margin-top: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* ═══════════════════════════════════════════════════════════
   空状态
   ═══════════════════════════════════════════════════════════ */

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-20) 0;
  text-align: center;
}

.empty-icon {
  color: var(--color-text-muted);
  margin-bottom: var(--space-6);
}

.empty-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin: 0 0 var(--space-2);
}

.empty-description {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  max-width: 400px;
  margin: 0;
}

/* ═══════════════════════════════════════════════════════════
   富文本内容 (v-html)
   ═══════════════════════════════════════════════════════════ */

.prose {
  /* 覆盖全局 typography.css 的 .prose { max-width: 65ch }：
     那条约 640px 的固定阅读宽度把正文钉死并左对齐，是内容偏窄、偏左的主因 */
  max-width: none;
  width: 100%;
  color: var(--color-text);
  line-height: var(--leading-relaxed);
}

.prose :deep(h1) {
  font-size: var(--text-4xl);
  font-weight: var(--font-bold);
  line-height: var(--leading-tight);
  margin-top: var(--space-12);
  margin-bottom: var(--space-6);
  color: var(--color-text);
}

.prose :deep(h2) {
  font-size: var(--text-3xl);
  font-weight: var(--font-semibold);
  line-height: var(--leading-tight);
  margin-top: var(--space-10);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text);
}

.prose :deep(h3) {
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  line-height: var(--leading-snug);
  margin-top: var(--space-8);
  margin-bottom: var(--space-3);
  color: var(--color-text);
}

.prose :deep(h4) {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  margin-top: var(--space-6);
  margin-bottom: var(--space-2);
  color: var(--color-text);
}

.prose :deep(p) {
  margin-top: var(--space-4);
  margin-bottom: var(--space-4);
  line-height: var(--leading-relaxed);
}

.prose :deep(a) {
  color: var(--color-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
  transition: color var(--transition-fast);
}

.prose :deep(a:hover) {
  color: var(--color-primary-dark);
}

.prose :deep(strong) {
  font-weight: var(--font-semibold);
  color: var(--color-text);
}

.prose :deep(code) {
  font-family: var(--font-mono);
  font-size: 0.875em;
  padding: 0.2em 0.4em;
  background-color: var(--color-gray-100);
  border-radius: var(--radius-sm);
  color: var(--color-text);
}

.prose :deep(blockquote) {
  margin: var(--space-6) 0;
  padding: var(--space-4) var(--space-6);
  border-left: 4px solid var(--color-primary);
  background-color: var(--color-gray-50);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  color: var(--color-text-secondary);
  font-style: italic;
}

.prose :deep(blockquote p) {
  margin: 0;
}

.prose :deep(ul) {
  margin: var(--space-4) 0;
  padding-left: var(--space-6);
  list-style: disc;
}

.prose :deep(ol) {
  margin: var(--space-4) 0;
  padding-left: var(--space-6);
  list-style: decimal;
}

.prose :deep(li) {
  margin-top: var(--space-1);
  margin-bottom: var(--space-1);
  padding-left: var(--space-1);
}

.prose :deep(hr) {
  border: none;
  border-top: 2px solid var(--color-border);
  margin: var(--space-10) 0;
}

.prose :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-lg);
  margin: var(--space-6) 0;
}

.prose :deep(.table-scroll) {
  width: 100%;
  margin: var(--space-6) 0;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.prose :deep(.table-scroll table) {
  width: 100%;
  /* 窄屏时列宽不低于此值，超出的部分由 .table-scroll 横向滚动 */
  min-width: 480px;
  border-collapse: collapse;
  margin: 0;
  font-size: var(--text-sm);
}

.prose :deep(thead) {
  background-color: var(--color-gray-50);
}

.prose :deep(th) {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  font-weight: var(--font-semibold);
  border-bottom: 2px solid var(--color-border);
  color: var(--color-text);
}

.prose :deep(td) {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.prose :deep(tbody tr:hover) {
  background-color: var(--color-gray-50);
}

.prose :deep(pre) {
  /* 代码块与正文同宽、左右边缘对齐正文，不做两侧出血；
     长行仍在本容器内横向滚动，不会撑开中间列 */
  margin: var(--space-6) 0;
  width: 100%;
  max-width: 100%;
  padding: var(--space-4) var(--space-6);
  background-color: var(--color-gray-900);
  color: #e5e7eb;
  border-radius: var(--radius-lg);
  overflow-x: auto;
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
}

.prose :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

/* ═══════════════════════════════════════════════════════════
   响应式
   ═══════════════════════════════════════════════════════════ */

@media (max-width: 1024px) {
  /* 只改 gutter，正文 padding 与代码块出血会一起跟着变 */
  .docs-page {
    --docs-gutter: clamp(20px, 3vw, 32px);
  }

  .content-wrapper {
    padding-top: var(--space-8);
    padding-bottom: var(--space-8);
  }
}

@media (max-width: 768px) {
  .docs-page {
    /* grid 下 flex-direction 无效，窄屏必须显式改回纵向 flex */
    display: flex;
    flex-direction: column;
    height: 100%;
    --docs-gutter: var(--space-4);
  }

  .docs-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--color-border);
  }

  .docs-content {
    flex: 1;
    min-height: 0;
  }

  .content-wrapper {
    padding-top: var(--space-6);
    padding-bottom: var(--space-6);
  }

  /* 窄屏隐藏目录 */
  .docs-toc {
    display: none;
  }
}

.nav-group {
  margin-bottom: var(--space-2);
}

.nav-group-title {
  padding: var(--space-2) var(--space-5);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* ═══════════════════════════════════════════════════════════
   右侧目录
   ═══════════════════════════════════════════════════════════ */
.docs-toc {
  width: 220px;
  flex-shrink: 0;
  background-color: var(--color-white);
  border-left: 1px solid var(--color-border);
  overflow-y: auto;
  padding: var(--space-6) var(--space-4);
}

.toc-header {
  margin-bottom: var(--space-3);
}

.toc-title {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.toc-nav ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.toc-nav li a {
  display: block;
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  border-left: 2px solid transparent;
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  transition: all var(--transition-fast);
  line-height: 1.5;
}

/* 层级区分：缩进 + 字重 + 颜色深浅。
   选择器写成 .toc-nav li.toc-level-N a 是为了抬高特异性，
   否则上面 padding 简写（含 padding-left）特异性更高会盖掉这里的 padding-left */
.toc-nav li.toc-level-1 a {
  font-weight: var(--font-semibold);
  color: var(--color-text);
}

.toc-nav li.toc-level-2 a {
  padding-left: var(--space-5);
}

.toc-nav li.toc-level-3 a {
  padding-left: var(--space-8);
  color: var(--color-text-muted);
}

.toc-nav li a:hover {
  color: var(--color-text);
  background-color: var(--color-gray-100);
}

.toc-nav li.active a {
  color: var(--color-primary);
  border-left-color: var(--color-primary);
  font-weight: var(--font-medium);
  background-color: var(--color-primary-lighter);
}

.toc-empty {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
}

/* 滚动定位时标题不要紧贴顶部 */
.prose :deep(h1),
.prose :deep(h2),
.prose :deep(h3) {
  scroll-margin-top: var(--space-4);
}
</style>